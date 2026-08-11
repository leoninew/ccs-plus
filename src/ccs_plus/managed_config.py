from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import portalocker
import tomlkit
from tomlkit import TOMLDocument

from ccs_plus.domain import AppKind, ProviderError, RuntimeProvider

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
    runtime: RuntimeProvider,
    state_home: Path,
    model: str | None,
    effort: str | None,
    *,
    user_home: Path | None = None,
) -> ManagedProfile:
    if runtime.provider.app is AppKind.CODEX:
        return _ensure_codex_profile(runtime, state_home, model, effort, user_home=user_home)
    if runtime.provider.app is AppKind.GROK:
        return _ensure_grok_model(runtime, state_home, model)
    raise ProviderError("Claude does not need a persistent managed configuration.")


def _ensure_codex_profile(
    runtime: RuntimeProvider,
    state_home: Path,
    model: str | None,
    effort: str | None,
    *,
    user_home: Path | None = None,
) -> ManagedProfile:
    profile = _managed_name(runtime, "codex")
    env_key = _managed_env_key(runtime, "CODEX")
    path = state_home / f"{profile}.config.toml"
    marker = _marker(runtime)
    approval_policy = _required(runtime.approval_policy, "Codex approval_policy")
    sandbox_mode = _required(runtime.sandbox_mode, "Codex sandbox_mode")
    with _locked(path):
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        if content and marker not in content:
            raise ProviderError(f"Refusing to overwrite unmanaged Codex profile: {path}")
        existing = _parse_codex_profile(content, path) if content else None

        document = tomlkit.document()
        document.add(tomlkit.comment(marker))
        document["model_provider"] = profile
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
        providers[profile] = provider
        document["model_providers"] = providers

        if user_home is not None:
            _merge_codex_user_tables(document, user_home)

        _write_atomic(path, tomlkit.dumps(document), locked=True, backup=path.exists())
    return ManagedProfile(name=profile, env_key=env_key)


def _merge_codex_user_tables(document: TOMLDocument, user_home: Path) -> None:
    config_path = user_home / "config.toml"
    if not config_path.is_file():
        return
    try:
        user_document = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Skipping Codex user config merge from %s: %s",
            config_path,
            exc,
        )
        return
    for key in CODEX_USER_CONFIG_TABLES:
        if key not in user_document:
            continue
        document[key] = deepcopy(user_document[key])


def _permission_profile(sandbox_mode: str) -> str:
    if sandbox_mode.startswith(":"):
        return sandbox_mode
    return f":{sandbox_mode}"


def _parse_codex_profile(content: str, path: Path) -> TOMLDocument:
    try:
        return tomlkit.parse(content)
    except Exception as exc:
        raise ProviderError(f"Managed Codex profile is invalid TOML: {path}: {exc}") from exc


def _ensure_grok_model(
    runtime: RuntimeProvider, state_home: Path, model: str | None
) -> ManagedProfile:
    profile = _managed_name(runtime, "grok")
    env_key = _managed_env_key(runtime, "GROK")
    path = state_home / "config.toml"
    marker = _marker(runtime)

    with _locked(path):
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        if content and profile in content and marker not in content:
            raise ProviderError(f"Refusing to overwrite unmanaged Grok model profile: {profile}")
        try:
            document = tomlkit.parse(content) if content else tomlkit.document()
        except Exception as exc:
            raise ProviderError(f"Grok config is invalid TOML: {path}: {exc}") from exc

        if marker not in content:
            document.add(tomlkit.comment(marker))
        model_tables = document.get("model")
        if model_tables is None:
            model_tables = tomlkit.table()
            document["model"] = model_tables
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


def _managed_name(runtime: RuntimeProvider, suffix: str) -> str:
    digest = sha256(runtime.provider.id.encode("utf-8")).hexdigest()[:16]
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
