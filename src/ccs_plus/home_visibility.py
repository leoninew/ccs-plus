"""Bring selected user-home state into isolated runtime homes."""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import tempfile
from collections.abc import Collection, Mapping, MutableMapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import portalocker
import tomlkit
from tomlkit import TOMLDocument

from ccs_plus.domain import (
    ClaudeRuntime,
    CodexRuntime,
    GrokRuntime,
    OpenCodeRuntime,
    ProviderError,
    RuntimeConfig,
)
from ccs_plus.settings import AppSettings, EntryVisibilitySettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HomeVisibility:
    """Prepare the user-owned state visible to one isolated runtime home."""

    state_home: Path
    user_home: Path | None
    profile_extension_keys: tuple[str, ...] = ()

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
    mcp_key: str = ""
    settings_keys: tuple[str, ...] = ()
    skills: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)
    plugins: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)

    def apply(self) -> None:
        if self.user_home is None:
            return
        link_user_entries(
            self.user_home / "skills",
            self.state_home / "skills",
            skip_names=self.skills.skip_names,
            copy_names=self.skills.copy_names,
        )
        link_user_entries(
            self.user_home / "plugins",
            self.state_home / "plugins",
            skip_names=self.plugins.skip_names,
            copy_names=self.plugins.copy_names,
        )
        self._merge_mcp_servers(self.user_home.parent / ".claude.json")
        self._merge_settings_keys()

    def _merge_settings_keys(self) -> None:
        """Project configured keys from the user settings.json into the isolated one.

        Plugin enablement and marketplace registrations must match the user home:
        the plugin cache is a shared junction, so an isolated sweep that sees
        fewer enabled plugins would mark the other home's cache entries orphaned.
        """
        if self.user_home is None or not self.settings_keys:
            return
        source_document = _read_json_object(
            self.user_home / "settings.json", "Claude settings source"
        )
        if source_document is None:
            return
        additions = {
            key: source_document[key] for key in self.settings_keys if key in source_document
        }
        if not additions:
            return

        target = self.state_home / "settings.json"
        existing_document = (
            _read_json_object(target, "Claude settings target") if target.exists() else {}
        )
        if existing_document is None:
            return
        output = dict(existing_document)
        changed = False
        for key, incoming in additions.items():
            merged_value = _merged_json_value(existing_document.get(key), incoming)
            if merged_value != existing_document.get(key):
                changed = True
            output[key] = merged_value
        if not changed:
            return
        try:
            _write_json_atomic(target, output)
        except OSError as exc:
            logger.warning("Failed to write Claude settings merge to %s: %s", target, exc)

    def _merge_mcp_servers(self, source: Path) -> None:
        source_document = _read_json_object(source, "Claude MCP source")
        if source_document is None:
            return
        user_servers = _mapping_or_empty(source_document.get(self.mcp_key), source)
        if user_servers is None:
            return

        target = self.state_home / ".claude.json"
        existing_document = (
            _read_json_object(target, "Claude MCP target") if target.exists() else {}
        )
        if existing_document is None:
            return
        existing_servers = _mapping_or_empty(existing_document.get(self.mcp_key), target)
        if existing_servers is None:
            return
        merged_servers = {**existing_servers, **user_servers}
        if merged_servers == existing_servers and self.mcp_key in existing_document:
            return
        output = dict(existing_document)
        output[self.mcp_key] = merged_servers
        try:
            _write_json_atomic(target, output)
        except OSError as exc:
            logger.warning("Failed to write Claude MCP merge to %s: %s", target, exc)


@dataclass(frozen=True)
class CodexHomeVisibility(HomeVisibility):
    is_official: bool = False
    project_directory: Path | None = None
    skills: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)
    plugins: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)

    def apply(self) -> None:
        if self.user_home is None:
            return
        self.expose_sessions()
        link_user_entries(
            self.user_home / "skills",
            self.state_home / "skills",
            skip_names=self.skills.skip_names,
            copy_names=self.skills.copy_names,
        )
        link_user_entries(
            self.user_home / "plugins",
            self.state_home / "plugins",
            skip_names=self.plugins.skip_names,
            copy_names=self.plugins.copy_names,
        )
        if self.is_official:
            self._merge_into_state()

    def expose_sessions(self) -> None:
        """Expose real Codex sessions for launch and TUI discovery."""
        if self.user_home is None or _path_key(self.state_home) == _path_key(self.user_home):
            return
        source = self.user_home / "sessions"
        target = self.state_home / "sessions"
        source_was_present = source.is_dir()
        try:
            source.mkdir(parents=True, exist_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"Failed to prepare Codex session paths: {exc}") from exc
        if not source_was_present and _path_lexists(target):
            return
        _link_one(source, target)

    def merge_into(self, document: TOMLDocument) -> None:
        state_document = _read_toml(self.state_home / "config.toml", "Codex state")
        user_document = (
            _read_toml(self.user_home / "config.toml", "Codex user")
            if self.user_home is not None
            else None
        )
        for key in self.profile_extension_keys:
            _merge_named_table(document, key, document, state_document, user_document)
        if user_document is not None:
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
            for key in self.profile_extension_keys:
                _merge_named_table(document, key, document, user_document)
            _merge_current_project_trust(document, user_document, self.project_directory)
            _write_toml_atomic(path, document)


@dataclass(frozen=True)
class GrokHomeVisibility(HomeVisibility):
    extension_keys: tuple[str, ...] = ()
    skills: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)
    plugins: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)
    hooks: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)
    installed_plugins: EntryVisibilitySettings = field(default_factory=EntryVisibilitySettings)

    def apply(self) -> None:
        if self.user_home is None or _path_key(self.state_home) == _path_key(self.user_home):
            return
        link_user_entries(
            self.user_home / "skills",
            self.state_home / "skills",
            skip_names=self.skills.skip_names,
            copy_names=self.skills.copy_names,
        )
        link_user_entries(
            self.user_home / "plugins",
            self.state_home / "plugins",
            skip_names=self.plugins.skip_names,
            copy_names=self.plugins.copy_names,
        )
        link_user_entries(
            self.user_home / "hooks",
            self.state_home / "hooks",
            skip_names=self.hooks.skip_names,
            copy_names=self.hooks.copy_names,
        )
        link_user_entries(
            self.user_home / "installed-plugins",
            self.state_home / "installed-plugins",
            skip_names=self.installed_plugins.skip_names,
            copy_names=self.installed_plugins.copy_names,
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
            for key in self.extension_keys:
                _merge_named_table(document, key, document, user_document)
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
        profile_extension_keys = (
            settings.codex.visibility.profile_extension_keys
            if isinstance(runtime, CodexRuntime)
            else ()
        )
        return DisabledHomeVisibility(
            state_home=state_home,
            user_home=None,
            profile_extension_keys=profile_extension_keys,
        )
    if isinstance(runtime, ClaudeRuntime):
        return ClaudeHomeVisibility(
            state_home=state_home,
            user_home=settings.claude.user_home,
            mcp_key=settings.claude.visibility.mcp_key,
            settings_keys=settings.claude.visibility.settings_keys,
            skills=settings.claude.visibility.skills,
            plugins=settings.claude.visibility.plugins,
        )
    if isinstance(runtime, CodexRuntime):
        return CodexHomeVisibility(
            state_home=state_home,
            user_home=settings.codex.user_home,
            profile_extension_keys=settings.codex.visibility.profile_extension_keys,
            is_official=runtime.provider.is_official,
            project_directory=project_directory,
            skills=settings.codex.visibility.skills,
            plugins=settings.codex.visibility.plugins,
        )
    if isinstance(runtime, GrokRuntime):
        return GrokHomeVisibility(
            state_home=state_home,
            user_home=settings.grok.user_home,
            extension_keys=settings.grok.visibility.extension_keys,
            skills=settings.grok.visibility.skills,
            plugins=settings.grok.visibility.plugins,
            hooks=settings.grok.visibility.hooks,
            installed_plugins=settings.grok.visibility.installed_plugins,
        )
    if isinstance(runtime, OpenCodeRuntime):
        return OpenCodeHomeVisibility(
            state_home=state_home,
            user_home=settings.opencode.user_home,
            is_official=runtime.provider.is_official,
            user_data_home=settings.opencode.user_data_home,
        )
    raise ProviderError(f"Unsupported home visibility runtime: {type(runtime).__name__}.")


@dataclass(frozen=True)
class OpenCodeHomeVisibility(HomeVisibility):
    """Link user OpenCode skills/plugins into the isolated config tree."""

    is_official: bool = False
    user_data_home: Path | None = None

    def apply(self) -> None:
        if self.user_home is not None:
            # User config lives at ~/.config/opencode; isolated at state/config/opencode.
            target_config = self.state_home / "config" / "opencode"
            target_config.mkdir(parents=True, exist_ok=True)
            for name in ("skills", "plugins", "agents", "commands", "tools", "themes"):
                link_user_entries(self.user_home / name, target_config / name)
        if self.is_official:
            self.expose_data()

    def expose_data(self) -> None:
        """Expose existing official auth and session state to the isolated home."""
        if self.user_data_home is None:
            return
        target = self.state_home / "share" / "opencode"
        if _path_key(target) == _path_key(self.user_data_home):
            return
        link_user_entries(self.user_data_home, target)


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

    Never links *source_dir* itself as a single unit. Source entries are
    authoritative: any conflicting target file, directory, or incorrect link
    is replaced. Dangling links are removed. Failures log a warning and do not
    raise.
    """
    try:
        if not source_dir.is_dir():
            return
        if _path_key(source_dir) == _path_key(target_dir):
            return
        lock_path = target_dir.parent / f".{target_dir.name}.ccs-plus.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(str(lock_path), timeout=30):
            _link_user_entries(source_dir, target_dir, skip_names, copy_names)
    except OSError as exc:
        logger.warning("Failed to prepare links from %s into %s: %s", source_dir, target_dir, exc)


def _link_user_entries(
    source_dir: Path,
    target_dir: Path,
    skip_names: Collection[str],
    copy_names: Collection[str],
) -> None:
    _prepare_target_directory(source_dir, target_dir)
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


def _merged_json_value(existing: object, incoming: object) -> object:
    """Union-merge mapping values (incoming wins on conflict); otherwise replace."""
    if isinstance(existing, Mapping) and isinstance(incoming, Mapping):
        merged = dict(existing)
        for name, value in incoming.items():
            merged[name] = deepcopy(value)
        return merged
    return deepcopy(incoming)


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
            _remove_target(entry)
            logger.warning("Removed dangling link %s", entry)
        except OSError as exc:
            logger.warning("Failed to remove dangling link %s: %s", entry, exc)


def _prepare_target_directory(source_dir: Path, target_dir: Path) -> None:
    """Keep an isolated entry container while rejecting conflicting roots."""
    if _path_lexists(target_dir) and (_is_link(target_dir) or not target_dir.is_dir()):
        _remove_target(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)


def _link_one(source: Path, target: Path) -> None:
    if _path_lexists(target):
        if _is_link(target) and _links_to(target, source):
            return
        try:
            _remove_target(target)
        except OSError as exc:
            logger.warning("Failed to replace target %s: %s", target, exc)
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
        if _path_lexists(target):
            _remove_target(target)
        shutil.copy2(source, target)
    except OSError as exc:
        logger.warning("Failed to copy %s -> %s: %s", target, source, exc)


def _remove_target(path: Path) -> None:
    """Remove a conflicting state entry without following directory links."""
    if _is_link(path):
        _remove_link(path)
    elif path.is_dir():
        shutil.rmtree(path, onerror=_remove_readonly_and_retry)
    else:
        _remove_readonly_and_retry(os.unlink, path, None)


def _remove_link(path: Path) -> None:
    try:
        if path.is_symlink():
            path.unlink()
        elif os.name == "nt":
            path.rmdir()
        else:
            path.unlink()
    except PermissionError:
        _make_writable(path)
        if path.is_symlink():
            path.unlink()
        elif os.name == "nt":
            path.rmdir()
        else:
            path.unlink()


def _remove_readonly_and_retry(function: object, path: str | Path, _exc_info: object) -> None:
    """Retry an rmtree operation after clearing a Windows read-only flag."""
    target = Path(path)
    _make_writable(target)
    cast(Any, function)(path)


def _make_writable(path: Path) -> None:
    if path.is_symlink():
        return
    try:
        mode = path.stat().st_mode
        os.chmod(path, mode | stat.S_IWRITE)
    except OSError:
        # Preserve the original removal error when attributes cannot be read or changed.
        raise


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
