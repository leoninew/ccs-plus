from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

import portalocker
import tomlkit
from tomlkit import TOMLDocument

from ccs_plus.domain import CodexRuntime, GrokRuntime, ProviderError, RuntimeProvider

logger = logging.getLogger(__name__)

CODEX_USER_CONFIG_TABLES = (
    "mcp_servers",
    "plugins",
    "marketplaces",
    "shell_environment_policy",
)


@dataclass(frozen=True)
class ManagedProfile:
    name: str
    env_key: str


def ensure_managed_config(
    runtime: CodexRuntime | GrokRuntime,
    state_home: Path,
    model: str | None,
    effort: str | None,
    *,
    user_home: Path | None = None,
    session_model_provider: str | None = None,
    project_directory: Path | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
) -> ManagedProfile:
    if isinstance(runtime, CodexRuntime):
        return _ensure_codex_profile(
            runtime,
            state_home,
            model,
            effort,
            user_home=user_home,
            project_directory=project_directory,
            session_model_provider=_required(
                session_model_provider,
                "Codex session_model_provider",
            ),
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
        )
    if isinstance(runtime, GrokRuntime):
        return _ensure_grok_model(runtime, state_home, model, effort)


def _ensure_codex_profile(
    runtime: CodexRuntime,
    state_home: Path,
    model: str | None,
    effort: str | None,
    *,
    user_home: Path | None = None,
    project_directory: Path | None = None,
    session_model_provider: str,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
) -> ManagedProfile:
    profile = _managed_name(runtime, "codex")
    env_key = _managed_env_key(runtime, "CODEX")
    path = state_home / f"{profile}.config.toml"
    marker = _marker(runtime)
    # Priority: explicit override (TUI) > provider config > settings default.
    # ``approval_policy``/``sandbox_mode`` args are treated as overrides when
    # set; callers that only want a settings fallback should pass them only
    # when the provider has no policy of its own (see launcher).
    approval_policy = _required(
        approval_policy or runtime.approval_policy,
        "Codex approval_policy",
    )
    sandbox_mode = _required(
        sandbox_mode or runtime.sandbox_mode,
        "Codex sandbox_mode",
    )
    with _locked(path):
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        if content and marker not in content:
            raise ProviderError(f"Refusing to overwrite unmanaged Codex profile: {path}")
        existing = _parse_codex_profile(content, path) if content else None

        document = tomlkit.document()
        document.add(tomlkit.comment(marker))
        # Codex filters the interactive /resume list by model_provider. Keep this
        # identity stable while the profile name continues to select a provider.
        document["model_provider"] = session_model_provider
        if model:
            document["model"] = model
        if effort:
            document["model_reasoning_effort"] = effort
        document["approval_policy"] = approval_policy
        # Codex permission profiles do not compose with legacy sandbox keys.
        # Map the provider's sandbox_mode onto the built-in permission profile.
        document["default_permissions"] = _permission_profile(sandbox_mode)

        if existing is not None:
            projects = existing.get("projects")
            if isinstance(projects, Mapping):
                document["projects"] = deepcopy(projects)

        providers = tomlkit.table()
        provider = tomlkit.table()
        provider["name"] = runtime.provider.name
        provider["base_url"] = _required(runtime.endpoint, "Codex provider endpoint")
        provider["wire_api"] = "responses"
        provider["env_key"] = env_key
        providers[session_model_provider] = provider
        document["model_providers"] = providers

        if user_home is not None:
            _merge_codex_user_tables(document, user_home, project_directory)

        _write_atomic(path, tomlkit.dumps(document), locked=True, backup=path.exists())
    return ManagedProfile(name=profile, env_key=env_key)


def _merge_codex_user_tables(
    document: TOMLDocument,
    user_home: Path,
    project_directory: Path | None = None,
) -> None:
    user_document = _load_codex_user_config(user_home)
    if user_document is None:
        return
    for key in CODEX_USER_CONFIG_TABLES:
        if key not in user_document:
            continue
        document[key] = deepcopy(user_document[key])
    _merge_current_project_trust(document, user_document, project_directory)


def sync_codex_user_config(
    state_home: Path,
    user_home: Path,
    project_directory: Path | None = None,
) -> None:
    """Copy user-owned Codex visibility tables into the isolated base config.

    Custom providers receive these tables in their managed profile. Official
    providers do not have such a profile, so their base config needs the same
    visibility layer. Provider, authentication, and unrelated user settings
    remain isolated in ``state_home``.
    """
    user_document = _load_codex_user_config(user_home)
    if user_document is None:
        return

    path = state_home / "config.toml"
    with _locked(path):
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        try:
            document = tomlkit.parse(content) if content else tomlkit.document()
        except Exception as exc:
            logger.warning("Skipping Codex user config merge into %s: %s", path, exc)
            return

        for key in CODEX_USER_CONFIG_TABLES:
            if key in user_document:
                document[key] = deepcopy(user_document[key])
        _merge_current_project_trust(document, user_document, project_directory)
        _write_atomic(path, tomlkit.dumps(document), locked=True, backup=path.exists())


def _load_codex_user_config(user_home: Path) -> TOMLDocument | None:
    config_path = user_home / "config.toml"
    if not config_path.is_file():
        return None
    try:
        return tomlkit.parse(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Skipping Codex user config merge from %s: %s",
            config_path,
            exc,
        )
        return None


def _merge_current_project_trust(
    document: TOMLDocument,
    user_document: TOMLDocument,
    project_directory: Path | None,
) -> None:
    if project_directory is None:
        return
    user_projects = user_document.get("projects")
    if not isinstance(user_projects, Mapping):
        return

    matching_key = _project_config_key(user_projects, project_directory)
    if matching_key is None:
        return

    projects = document.get("projects")
    if not isinstance(projects, Mapping):
        projects = tomlkit.table()
        document["projects"] = projects
    projects = cast(MutableMapping[str, object], projects)
    projects[matching_key] = deepcopy(user_projects[matching_key])


def _project_config_key(projects: Mapping[object, object], directory: Path) -> str | None:
    """Find the trusted project root containing the requested working directory."""
    current = os.path.normcase(os.path.abspath(os.path.normpath(str(directory))))
    matches: list[str] = []
    for key in projects:
        if not isinstance(key, str):
            continue
        candidate = os.path.normcase(os.path.abspath(os.path.normpath(key)))
        try:
            if os.path.commonpath((candidate, current)) == candidate:
                matches.append(key)
        except ValueError:
            # Windows paths on different drives cannot share a project root.
            continue
    return max(matches, key=len, default=None)


def _permission_profile(sandbox_mode: str) -> str:
    """Map legacy sandbox_mode values onto Codex built-in permission profiles.

    Codex accepts built-ins ``:read-only``, ``:workspace``, and
    ``:danger-full-access``. The historical sandbox key ``workspace-write``
    maps to ``:workspace``.
    """
    name = sandbox_mode[1:] if sandbox_mode.startswith(":") else sandbox_mode
    aliases = {
        "workspace-write": "workspace",
        "workspace_write": "workspace",
        "read_only": "read-only",
        "danger_full_access": "danger-full-access",
    }
    return f":{aliases.get(name, name)}"


def _parse_codex_profile(content: str, path: Path) -> TOMLDocument:
    try:
        return tomlkit.parse(content)
    except Exception as exc:
        raise ProviderError(f"Managed Codex profile is invalid TOML: {path}: {exc}") from exc


def _ensure_grok_model(
    runtime: GrokRuntime, state_home: Path, model: str | None, effort: str | None
) -> ManagedProfile:
    profile = _managed_name(runtime, "grok")
    env_key = _managed_env_key(runtime, "GROK")
    path = state_home / "config.toml"
    marker = _marker(runtime)

    with _locked(path):
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        try:
            document = tomlkit.parse(content) if content else tomlkit.document()
        except Exception as exc:
            raise ProviderError(f"Grok config is invalid TOML: {path}: {exc}") from exc

        if _unmanaged_grok_profile(document, profile, env_key, content, marker):
            raise ProviderError(f"Refusing to overwrite unmanaged Grok model profile: {profile}")

        if marker not in content:
            document.add(tomlkit.comment(marker))
        models = document.get("models")
        if models is None:
            models = tomlkit.table()
            document["models"] = models
        if not isinstance(models, MutableMapping):
            raise ProviderError("Grok models configuration is invalid.")
        if effort:
            models["default_reasoning_effort"] = effort
        else:
            models.pop("default_reasoning_effort", None)
        model_tables = document.get("model")
        if model_tables is None:
            model_tables = tomlkit.table()
            document["model"] = model_tables
        _remove_stale_managed_grok_models(models, model_tables, profile)
        target = tomlkit.table()
        target["model"] = model or _required(runtime.model, "Grok model")
        target["base_url"] = _required(runtime.endpoint, "Grok provider endpoint")
        target["name"] = runtime.provider.name
        target["env_key"] = env_key
        target["api_backend"] = "responses"
        target["context_window"] = 500_000
        model_tables[profile] = target
        _write_atomic(path, tomlkit.dumps(document), locked=True, backup=path.exists())
    return ManagedProfile(name=profile, env_key=env_key)


def _remove_stale_managed_grok_models(
    models: MutableMapping[str, object],
    model_tables: MutableMapping[str, object],
    current_profile: str,
) -> None:
    for name, value in list(model_tables.items()):
        if name == current_profile or not _is_managed_grok_model(name, value):
            continue
        del model_tables[name]
        if models.get("default") == name:
            models.pop("default", None)


def _is_managed_grok_model(name: object, value: object) -> bool:
    if not isinstance(name, str) or not isinstance(value, Mapping):
        return False
    digest = name.removeprefix("ccs-plus-grok-")
    if len(digest) != 16 or any(character not in "0123456789abcdef" for character in digest):
        return False
    env_key = value.get("env_key")
    return (
        isinstance(env_key, str)
        and env_key.startswith("CCS_PLUS_GROK_")
        and env_key.endswith("_API_KEY")
    )


def _unmanaged_grok_profile(
    document: TOMLDocument,
    profile: str,
    env_key: str,
    content: str,
    marker: str,
) -> bool:
    """Return True when ``profile`` exists and is not owned by this provider.

    Ownership is the comment marker or a matching ``env_key``. Grok rewrites
    the shared ``config.toml`` and drops comments, so the marker alone is not
    a durable claim on a table this process previously wrote.
    """
    model_tables = document.get("model")
    if not isinstance(model_tables, Mapping) or profile not in model_tables:
        return False
    if marker in content:
        return False
    existing = model_tables.get(profile)
    return not (isinstance(existing, Mapping) and existing.get("env_key") == env_key)


def _managed_name(runtime: RuntimeProvider, suffix: str) -> str:
    return _managed_name_for_provider_id(runtime.provider.id, suffix)


def remove_managed_codex_profile(state_home: Path, provider_id: str) -> bool:
    """Remove one ccs-plus-owned Codex profile after its provider is deleted."""
    profile = _managed_name_for_provider_id(provider_id, "codex")
    path = state_home / f"{profile}.config.toml"
    marker = f"ccs-plus-managed: codex:{provider_id}"
    with _locked(path):
        if not path.is_file():
            return False
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Unable to read Codex profile for cleanup %s: %s", path, exc)
            return False
        if marker not in content:
            logger.warning("Refusing to delete unmanaged Codex profile: %s", path)
            return False
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Unable to delete Codex profile %s: %s", path, exc)
            return False
    return True


def _managed_name_for_provider_id(provider_id: str, suffix: str) -> str:
    digest = sha256(provider_id.encode("utf-8")).hexdigest()[:16]
    return f"ccs-plus-{suffix}-{digest}"


def _managed_env_key(runtime: RuntimeProvider, app: str) -> str:
    digest = sha256(runtime.provider.id.encode("utf-8")).hexdigest()[:16].upper()
    return f"CCS_PLUS_{app}_{digest}_API_KEY"


def _marker(runtime: RuntimeProvider) -> str:
    return f"ccs-plus-managed: {runtime.provider.app.value}:{runtime.provider.id}"


def _required(value: str | None, label: str) -> str:
    if not value:
        raise ProviderError(f"{label} is required.")
    return value


class _locked:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock: portalocker.Lock | None = None

    def __enter__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.lock = portalocker.Lock(str(lock_path), timeout=5)
        self.lock.acquire()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.lock is not None:
            self.lock.release()


def _write_atomic(path: Path, content: str, locked: bool = False, backup: bool = False) -> None:
    if locked:
        _write(path, content, backup=backup)
        return
    with _locked(path):
        _write(path, content, backup=backup)


def _write(path: Path, content: str, backup: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".ccs-plus.bak"))
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
