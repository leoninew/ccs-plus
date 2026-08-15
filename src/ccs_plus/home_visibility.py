"""Bring selected user-home state into isolated runtime homes."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Collection, Mapping, MutableMapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import portalocker
import tomlkit
from tomlkit import TOMLDocument

from ccs_plus.domain import ClaudeRuntime, CodexRuntime, GrokRuntime, ProviderError, RuntimeConfig
from ccs_plus.settings import AppSettings

logger = logging.getLogger(__name__)

CLAUDE_MCP_KEY = "mcpServers"


@dataclass(frozen=True)
class HomeVisibility:
    """Prepare the user-owned state visible to one isolated runtime home."""

    state_home: Path
    user_home: Path | None

    def apply(self) -> None:
        raise NotImplementedError

    def merge_into(self, document: TOMLDocument) -> None:
        """Add user-visible configuration to a generated managed profile."""


@dataclass(frozen=True)
class DisabledHomeVisibility(HomeVisibility):
    """Disable user-home propagation for launches rooted at the user Home."""

    def apply(self) -> None:
        pass


@dataclass(frozen=True)
class ClaudeHomeVisibility(HomeVisibility):
    plugin_copy_names: Collection[str] = ()
    plugin_skip_names: Collection[str] = ()

    def apply(self) -> None:
        if self.user_home is None:
            return
        link_user_entries(self.user_home / "skills", self.state_home / "skills")
        link_user_entries(
            self.user_home / "plugins",
            self.state_home / "plugins",
            skip_names=self.plugin_skip_names,
            copy_names=self.plugin_copy_names,
        )
        self._merge_mcp_servers(self.user_home.parent / ".claude.json")

    def _merge_mcp_servers(self, source: Path) -> None:
        source_document = _read_json_object(source, "Claude MCP source")
        if source_document is None:
            return
        user_servers = _mapping_or_empty(source_document.get(CLAUDE_MCP_KEY), source)
        if user_servers is None:
            return

        target = self.state_home / ".claude.json"
        existing_document = (
            _read_json_object(target, "Claude MCP target") if target.exists() else {}
        )
        if existing_document is None:
            return
        existing_servers = _mapping_or_empty(existing_document.get(CLAUDE_MCP_KEY), target)
        if existing_servers is None:
            return
        merged_servers = {**existing_servers, **user_servers}
        if merged_servers == existing_servers and CLAUDE_MCP_KEY in existing_document:
            return
        output = dict(existing_document)
        output[CLAUDE_MCP_KEY] = merged_servers
        try:
            _write_json_atomic(target, output)
        except OSError as exc:
            logger.warning("Failed to write Claude MCP merge to %s: %s", target, exc)


@dataclass(frozen=True)
class CodexHomeVisibility(HomeVisibility):
    is_official: bool = False
    project_directory: Path | None = None

    def apply(self) -> None:
        if self.user_home is None:
            return
        self.expose_sessions()
        link_user_entries(
            self.user_home / "skills",
            self.state_home / "skills",
            skip_names={".system"},
        )
        link_user_entries(
            self.user_home / "plugins",
            self.state_home / "plugins",
            skip_names={".plugin-appserver", ".remote-plugin-install-staging"},
        )
        if self.is_official:
            self._merge_into_state()

    def expose_sessions(self) -> None:
        """Expose real Codex sessions for launch and TUI discovery."""
        if self.user_home is None or _path_key(self.state_home) == _path_key(self.user_home):
            return
        source = self.user_home / "sessions"
        target = self.state_home / "sessions"
        try:
            source.mkdir(parents=True, exist_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"Failed to prepare Codex session paths: {exc}") from exc
        if _path_lexists(target):
            return
        try:
            _link_directory(source, target)
        except OSError as exc:
            logger.warning("Failed to link Codex sessions %s -> %s: %s", target, source, exc)

    def merge_into(self, document: TOMLDocument) -> None:
        state_document = _read_toml(self.state_home / "config.toml", "Codex state")
        user_document = (
            _read_toml(self.user_home / "config.toml", "Codex user")
            if self.user_home is not None
            else None
        )
        _merge_named_table(document, "mcp_servers", state_document, user_document)
        if user_document is None:
            return
        for key in ("plugins", "marketplaces", "shell_environment_policy"):
            if key in user_document:
                document[key] = deepcopy(user_document[key])
        _merge_current_project_trust(document, user_document, self.project_directory)

    def _merge_into_state(self) -> None:
        if self.user_home is None:
            return
        user_document = _read_toml(self.user_home / "config.toml", "Codex user")
        if user_document is None:
            return
        path = self.state_home / "config.toml"
        with _toml_lock(path):
            document = _read_toml(path, "Codex state") if path.exists() else tomlkit.document()
            if document is None:
                return
            _merge_named_table(document, "mcp_servers", document, user_document)
            for key in ("plugins", "marketplaces", "shell_environment_policy"):
                if key in user_document:
                    document[key] = deepcopy(user_document[key])
            _merge_current_project_trust(document, user_document, self.project_directory)
            _write_toml_atomic(path, document)


@dataclass(frozen=True)
class GrokHomeVisibility(HomeVisibility):
    def apply(self) -> None:
        if self.user_home is None or _path_key(self.state_home) == _path_key(self.user_home):
            return
        link_user_entries(self.user_home / "skills", self.state_home / "skills")
        link_user_entries(self.user_home / "plugins", self.state_home / "plugins")
        link_user_entries(self.user_home / "hooks", self.state_home / "hooks")
        link_user_entries(
            self.user_home / "installed-plugins",
            self.state_home / "installed-plugins",
            copy_names={"registry.json"},
        )
        self._merge_user_config()

    def _merge_user_config(self) -> None:
        if self.user_home is None:
            return
        user_document = _read_toml(self.user_home / "config.toml", "Grok user")
        if user_document is None:
            return
        path = self.state_home / "config.toml"
        with _toml_lock(path):
            document = _read_toml(path, "Grok state") if path.exists() else tomlkit.document()
            if document is None:
                return
            _merge_named_table(document, "mcp_servers", document, user_document)
            for key in ("skills", "plugins", "marketplace", "hooks"):
                if key in user_document:
                    document[key] = deepcopy(user_document[key])
            _write_toml_atomic(path, document)


def home_visibility_for(
    runtime: RuntimeConfig,
    settings: AppSettings,
    state_home: Path,
    project_directory: Path | None = None,
    *,
    enabled: bool = True,
) -> HomeVisibility:
    """Build the visibility policy matching *runtime*."""
    if not enabled:
        return DisabledHomeVisibility(state_home=state_home, user_home=None)
    if isinstance(runtime, ClaudeRuntime):
        return ClaudeHomeVisibility(
            state_home=state_home,
            user_home=settings.claude.user_home,
            plugin_copy_names=settings.claude.plugin_copy_names,
            plugin_skip_names=settings.claude.plugin_skip_names,
        )
    if isinstance(runtime, CodexRuntime):
        return CodexHomeVisibility(
            state_home=state_home,
            user_home=settings.codex.user_home,
            is_official=runtime.provider.is_official,
            project_directory=project_directory,
        )
    if isinstance(runtime, GrokRuntime):
        return GrokHomeVisibility(state_home=state_home, user_home=settings.grok.user_home)
    raise ProviderError(f"Unsupported home visibility runtime: {type(runtime).__name__}.")


def link_user_entries(
    source_dir: Path,
    target_dir: Path,
    *,
    skip_names: Collection[str] = (),
    copy_names: Collection[str] = (),
) -> None:
    """Link each entry under *source_dir* into *target_dir* individually.

    Directories are junctioned/symlinked so both sides share one tree. File
    names listed in *copy_names* are copied from source on every call, replacing
    any stale target copy — index/state files whose contents point back at the
    real home need no link. Other files are hardlinked then symlinked. Names in
    *skip_names* are never touched on the target side.

    Never links *source_dir* itself as a single unit. Existing real entries in
    *target_dir* are left untouched. Dangling links are removed. Failures log a
    warning and do not raise.
    """
    try:
        if not source_dir.is_dir():
            return
        target_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_dangling_links(target_dir)
        skip = set(skip_names)
        copy = set(copy_names)
        for source_entry in sorted(source_dir.iterdir(), key=lambda path: path.name.lower()):
            name = source_entry.name
            if name in skip:
                continue
            target_entry = target_dir / name
            if name in copy and source_entry.is_file():
                _copy_file(source_entry, target_entry)
            else:
                _link_one(source_entry, target_entry)
    except OSError as exc:
        logger.warning("Failed to prepare links from %s into %s: %s", source_dir, target_dir, exc)


def _read_json_object(path: Path, label: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning("Skipping %s; invalid JSON in %s: %s", label, path, exc)
        return None
    if not isinstance(document, dict):
        logger.warning("Skipping %s; root is not an object: %s", label, path)
        return None
    return document


def _mapping_or_empty(value: object, path: Path) -> dict[str, Any] | None:
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning("Skipping visibility merge; expected an object in %s", path)
        return None
    return value


def _read_toml(path: Path, label: str) -> TOMLDocument | None:
    if not path.is_file():
        return None
    try:
        return tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Skipping %s config from %s: %s", label, path, exc)
        return None


def _merge_named_table(
    document: TOMLDocument,
    key: str,
    *sources: TOMLDocument | None,
) -> None:
    merged = tomlkit.table()
    found = False
    for source in sources:
        if source is None:
            continue
        values = source.get(key)
        if not isinstance(values, Mapping):
            continue
        for name, value in values.items():
            merged[name] = deepcopy(value)
            found = True
    if found:
        document[key] = merged


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
    cast(MutableMapping[str, object], projects)[matching_key] = deepcopy(
        user_projects[matching_key]
    )


def _project_config_key(projects: Mapping[object, object], directory: Path) -> str | None:
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
            continue
    return max(matches, key=len, default=None)


def _cleanup_dangling_links(target_dir: Path) -> None:
    try:
        entries = list(target_dir.iterdir())
    except OSError as exc:
        logger.warning("Failed to scan %s for dangling links: %s", target_dir, exc)
        return
    for entry in entries:
        if not _is_link(entry):
            continue
        if _link_destination_exists(entry):
            continue
        try:
            entry.unlink(missing_ok=True)
            logger.warning("Removed dangling link %s", entry)
        except OSError as exc:
            logger.warning("Failed to remove dangling link %s: %s", entry, exc)


def _link_one(source: Path, target: Path) -> None:
    if _path_lexists(target):
        if _is_link(target) and _links_to(target, source):
            return
        if _is_link(target) and not _link_destination_exists(target):
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to replace dangling link %s: %s", target, exc)
                return
        else:
            # Real entry or link to a different target: isolation side wins.
            return

    try:
        if source.is_dir() and not source.is_symlink():
            _link_directory(source, target)
        else:
            _link_file(source, target)
    except FileExistsError:
        return
    except OSError as exc:
        logger.warning("Failed to link %s -> %s: %s", target, source, exc)


def _link_directory(source: Path, target: Path) -> None:
    if os.name == "nt":
        _create_windows_junction(source, target)
        return
    target.symlink_to(source, target_is_directory=True)


def _create_windows_junction(source: Path, target: Path) -> None:
    import _winapi

    # CreateJunction(source_dir, junction_path) makes junction_path point at source_dir.
    _winapi.CreateJunction(str(source), str(target))


def _link_file(source: Path, target: Path) -> None:
    try:
        os.link(source, target)
        return
    except OSError:
        pass
    try:
        target.symlink_to(source)
    except OSError as exc:
        logger.warning("Failed to link file %s -> %s: %s", target, source, exc)


def _copy_file(source: Path, target: Path) -> None:
    """Copy *source* into *target*, replacing any stale isolated copy.

    An existing link that already points back at *source* is kept as-is.
    """
    if _is_link(target) and _links_to(target, source):
        return
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        logger.warning("Failed to copy %s -> %s: %s", target, source, exc)


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return True
        except OSError:
            return False
    if os.name == "nt" and _path_lexists(path):
        try:
            os.readlink(path)
            return True
        except OSError:
            return False
    return False


def _link_destination_exists(link: Path) -> bool:
    destination = _read_link_destination(link)
    if destination is None:
        return False
    return destination.exists()


def _links_to(link: Path, source: Path) -> bool:
    destination = _read_link_destination(link)
    if destination is None:
        return False
    return _path_key(destination) == _path_key(source)


def _read_link_destination(link: Path) -> Path | None:
    try:
        destination = Path(os.readlink(link))
    except OSError:
        return None
    if not destination.is_absolute():
        destination = link.parent / destination
    return _strip_extended_path(destination)


def _strip_extended_path(path: Path) -> Path:
    text = os.fspath(path)
    if text.startswith("\\\\?\\") or text.startswith("//?/"):
        text = text[4:]
    return Path(text)


def _path_key(path: Path) -> str:
    try:
        resolved = _strip_extended_path(path).resolve()
    except OSError:
        resolved = _strip_extended_path(path)
    return os.path.normcase(os.fspath(resolved))


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    lock_path = path.with_suffix(path.suffix + ".lock")
    with portalocker.Lock(str(lock_path), timeout=5):
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


def _toml_lock(path: Path) -> portalocker.Lock:
    path.parent.mkdir(parents=True, exist_ok=True)
    return portalocker.Lock(str(path.with_suffix(path.suffix + ".lock")), timeout=5)


def _write_toml_atomic(path: Path, document: TOMLDocument) -> None:
    payload = tomlkit.dumps(document)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
