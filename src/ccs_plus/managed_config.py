from __future__ import annotations

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

_CODEX_PERMISSION_PROFILE = "ccs_plus_workspace_net"


@dataclass(frozen=True)
class ManagedProfile:
    name: str
    env_key: str


def ensure_managed_config(
    runtime: RuntimeProvider,
    state_home: Path,
    model: str | None,
    effort: str | None,
) -> ManagedProfile:
    if runtime.provider.app is AppKind.CODEX:
        return _ensure_codex_profile(runtime, state_home, model, effort)
    if runtime.provider.app is AppKind.GROK:
        return _ensure_grok_model(runtime, state_home, model)
    raise ProviderError("Claude does not need a persistent managed configuration.")


def _ensure_codex_profile(
    runtime: RuntimeProvider,
    state_home: Path,
    model: str | None,
    effort: str | None,
) -> ManagedProfile:
    profile = _managed_name(runtime, "codex")
    env_key = _managed_env_key(runtime, "CODEX")
    path = state_home / f"{profile}.config.toml"
    marker = _marker(runtime)
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
        document["approval_policy"] = "never"
        document["default_permissions"] = _CODEX_PERMISSION_PROFILE

        # Codex writes these choices back into the selected profile. Retain them
        # across reconciliation so native Windows sandbox setup is not repeated.
        if existing is not None:
            projects = existing.get("projects")
            if isinstance(projects, Mapping):
                document["projects"] = deepcopy(projects)
        windows = tomlkit.table()
        windows["sandbox"] = _existing_windows_sandbox(existing)
        document["windows"] = windows

        permissions = tomlkit.table()
        workspace_network = tomlkit.table()
        workspace_network["extends"] = ":workspace"
        network = tomlkit.table()
        network["enabled"] = True
        domains = tomlkit.table()
        domains["*"] = "allow"
        network["domains"] = domains
        workspace_network["network"] = network
        permissions[_CODEX_PERMISSION_PROFILE] = workspace_network
        document["permissions"] = permissions

        providers = tomlkit.table()
        provider = tomlkit.table()
        provider["name"] = runtime.provider.name
        provider["base_url"] = _required(runtime.endpoint, "Codex provider endpoint")
        provider["wire_api"] = "responses"
        provider["env_key"] = env_key
        providers[profile] = provider
        document["model_providers"] = providers

        _write_atomic(path, tomlkit.dumps(document), locked=True, backup=path.exists())
    return ManagedProfile(name=profile, env_key=env_key)


def _parse_codex_profile(content: str, path: Path) -> TOMLDocument:
    try:
        return tomlkit.parse(content)
    except Exception as exc:
        raise ProviderError(f"Managed Codex profile is invalid TOML: {path}: {exc}") from exc


def _existing_windows_sandbox(document: object) -> str:
    if isinstance(document, Mapping):
        windows = document.get("windows")
        if isinstance(windows, Mapping):
            mode = str(windows.get("sandbox", ""))
            if mode in {"elevated", "unelevated"}:
                return mode
    return "elevated"


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
