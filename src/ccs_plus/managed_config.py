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

import portalocker
import tomlkit
from tomlkit import TOMLDocument

from ccs_plus.domain import CodexRuntime, GrokRuntime, ProviderError, RuntimeProvider
from ccs_plus.home_visibility import HomeVisibility

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManagedProfile:
    name: str
    env_key: str


@dataclass(frozen=True)
class ManagedConfig:
    runtime: RuntimeProvider
    state_home: Path
    model: str | None
    effort: str | None

    def ensure(self) -> ManagedProfile:
        raise NotImplementedError


@dataclass(frozen=True)
class CodexManagedConfig(ManagedConfig):
    runtime: CodexRuntime
    session_model_provider: str
    approval_policy: str | None = None
    sandbox_mode: str | None = None
    visibility: HomeVisibility | None = None

    def ensure(self) -> ManagedProfile:
        profile = _managed_name(self.runtime, "codex")
        env_key = _managed_env_key(self.runtime, "CODEX")
        path = self.state_home / f"{profile}.config.toml"
        marker = _marker(self.runtime)
        approval_policy = _required(
            self.approval_policy or self.runtime.approval_policy,
            "Codex approval_policy",
        )
        sandbox_mode = _required(
            self.sandbox_mode or self.runtime.sandbox_mode,
            "Codex sandbox_mode",
        )
        with _locked(path):
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            if content and marker not in content:
                raise ProviderError(f"Refusing to overwrite unmanaged Codex profile: {path}")
            existing = self._parse(content, path) if content else None
            document = tomlkit.document()
            document.add(tomlkit.comment(marker))
            document["model_provider"] = self.session_model_provider
            if self.model:
                document["model"] = self.model
            if self.effort:
                document["model_reasoning_effort"] = self.effort
            document["approval_policy"] = approval_policy
            document["default_permissions"] = self._permission_profile(sandbox_mode)
            if existing is not None:
                projects = existing.get("projects")
                if isinstance(projects, Mapping):
                    document["projects"] = deepcopy(projects)
            providers = tomlkit.table()
            provider = tomlkit.table()
            provider["name"] = self.runtime.provider.name
            provider["base_url"] = _required(
                self.runtime.endpoint,
                "Codex provider endpoint",
            )
            provider["wire_api"] = "responses"
            provider["env_key"] = env_key
            providers[self.session_model_provider] = provider
            document["model_providers"] = providers
            if self.visibility is not None:
                self.visibility.merge_into(document)
            _write_atomic(path, tomlkit.dumps(document), locked=True, backup=path.exists())
        return ManagedProfile(name=profile, env_key=env_key)

    @staticmethod
    def _permission_profile(sandbox_mode: str) -> str:
        name = sandbox_mode[1:] if sandbox_mode.startswith(":") else sandbox_mode
        aliases = {
            "workspace-write": "workspace",
            "workspace_write": "workspace",
            "read_only": "read-only",
            "danger_full_access": "danger-full-access",
        }
        return f":{aliases.get(name, name)}"

    @staticmethod
    def _parse(content: str, path: Path) -> TOMLDocument:
        try:
            return tomlkit.parse(content)
        except Exception as exc:
            raise ProviderError(f"Managed Codex profile is invalid TOML: {path}: {exc}") from exc

    @staticmethod
    def remove(state_home: Path, provider_id: str) -> bool:
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


@dataclass(frozen=True)
class GrokManagedConfig(ManagedConfig):
    runtime: GrokRuntime

    def ensure(self) -> ManagedProfile:
        profile = _managed_name(self.runtime, "grok")
        env_key = _managed_env_key(self.runtime, "GROK")
        path = self.state_home / "config.toml"
        marker = _marker(self.runtime)
        with _locked(path):
            content = path.read_text(encoding="utf-8") if path.exists() else ""
            try:
                document = tomlkit.parse(content) if content else tomlkit.document()
            except Exception as exc:
                raise ProviderError(f"Grok config is invalid TOML: {path}: {exc}") from exc
            if self._is_unmanaged(document, profile, env_key, content, marker):
                raise ProviderError(
                    f"Refusing to overwrite unmanaged Grok model profile: {profile}"
                )
            if marker not in content:
                document.add(tomlkit.comment(marker))
            models = document.get("models")
            if models is None:
                models = tomlkit.table()
                document["models"] = models
            if not isinstance(models, MutableMapping):
                raise ProviderError("Grok models configuration is invalid.")
            if self.effort:
                models["default_reasoning_effort"] = self.effort
            else:
                models.pop("default_reasoning_effort", None)
            model_tables = document.get("model")
            if model_tables is None:
                model_tables = tomlkit.table()
                document["model"] = model_tables
            self._remove_stale(models, model_tables, profile)
            target = tomlkit.table()
            target["model"] = self.model or _required(self.runtime.model, "Grok model")
            target["base_url"] = _required(self.runtime.endpoint, "Grok provider endpoint")
            target["name"] = self.runtime.provider.name
            target["env_key"] = env_key
            target["api_backend"] = "responses"
            target["context_window"] = 500_000
            model_tables[profile] = target
            _write_atomic(path, tomlkit.dumps(document), locked=True, backup=path.exists())
        return ManagedProfile(name=profile, env_key=env_key)

    @classmethod
    def _remove_stale(
        cls,
        models: MutableMapping[str, object],
        model_tables: MutableMapping[str, object],
        current_profile: str,
    ) -> None:
        for name, value in list(model_tables.items()):
            if name == current_profile or not cls._is_owned(name, value):
                continue
            del model_tables[name]
            if models.get("default") == name:
                models.pop("default", None)

    @staticmethod
    def _is_owned(name: object, value: object) -> bool:
        if not isinstance(name, str) or not isinstance(value, Mapping):
            return False
        digest = name.removeprefix("ccs-plus-grok-")
        if len(digest) != 16 or any(char not in "0123456789abcdef" for char in digest):
            return False
        env_key = value.get("env_key")
        return (
            isinstance(env_key, str)
            and env_key.startswith("CCS_PLUS_GROK_")
            and env_key.endswith("_API_KEY")
        )

    @staticmethod
    def _is_unmanaged(
        document: TOMLDocument,
        profile: str,
        env_key: str,
        content: str,
        marker: str,
    ) -> bool:
        model_tables = document.get("model")
        if not isinstance(model_tables, Mapping) or profile not in model_tables:
            return False
        if marker in content:
            return False
        existing = model_tables.get(profile)
        return not (isinstance(existing, Mapping) and existing.get("env_key") == env_key)


def ensure_managed_config(
    runtime: CodexRuntime | GrokRuntime,
    state_home: Path,
    model: str | None,
    effort: str | None,
    *,
    session_model_provider: str | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    visibility: HomeVisibility | None = None,
) -> ManagedProfile:
    if isinstance(runtime, CodexRuntime):
        return CodexManagedConfig(
            runtime=runtime,
            state_home=state_home,
            model=model,
            effort=effort,
            session_model_provider=_required(
                session_model_provider,
                "Codex session_model_provider",
            ),
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            visibility=visibility,
        ).ensure()
    if isinstance(runtime, GrokRuntime):
        return GrokManagedConfig(runtime, state_home, model, effort).ensure()
    raise ProviderError(f"Unsupported managed config runtime: {type(runtime).__name__}.")


def _managed_name(runtime: RuntimeProvider, suffix: str) -> str:
    return _managed_name_for_provider_id(runtime.provider.id, suffix)


def remove_managed_config(state_home: Path, provider_id: str) -> bool:
    """Remove the ccs-plus-owned managed config associated with a provider."""
    return CodexManagedConfig.remove(state_home, provider_id)


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
