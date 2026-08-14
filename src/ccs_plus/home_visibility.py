"""Bring selected user-home state into isolated runtime homes."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Collection
from pathlib import Path
from typing import Any

import portalocker

logger = logging.getLogger(__name__)

CLAUDE_MCP_KEY = "mcpServers"


def link_user_entries(
    source_dir: Path,
    target_dir: Path,
    *,
    skip_names: Collection[str] = (),
) -> None:
    """Link each entry under *source_dir* into *target_dir* individually.

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
        for source_entry in sorted(source_dir.iterdir(), key=lambda path: path.name.lower()):
            name = source_entry.name
            if name in skip:
                continue
            target_entry = target_dir / name
            _link_one(source_entry, target_entry)
    except OSError as exc:
        logger.warning("Failed to prepare links from %s into %s: %s", source_dir, target_dir, exc)


def apply_codex_visibility(state_home: Path, user_home: Path) -> None:
    link_codex_sessions(state_home, user_home)
    link_user_entries(user_home / "skills", state_home / "skills", skip_names={".system"})
    link_user_entries(user_home / "plugins", state_home / "plugins")


def link_codex_sessions(state_home: Path, user_home: Path) -> None:
    """Expose the real Codex session store without sharing the rest of its home.

    ``state_home`` remains the provider-isolated ``CODEX_HOME``. Existing
    state-home content remains untouched.
    """
    if _path_key(state_home) == _path_key(user_home):
        return

    source = user_home / "sessions"
    target = state_home / "sessions"
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


def apply_claude_visibility(state_home: Path, user_home: Path) -> None:
    link_user_entries(user_home / "skills", state_home / "skills")
    link_user_entries(user_home / "plugins", state_home / "plugins")
    sync_claude_mcp_servers(state_home, source_path=user_home.parent / ".claude.json")


def sync_claude_mcp_servers(
    state_home: Path,
    source_path: Path | None = None,
) -> None:
    """Merge user-level mcpServers into the isolated Claude state file.

    Source defaults to ``Path.home() / ".claude.json"``. Callers that use a
    configured Claude user home pass its sibling ``.claude.json`` explicitly.
    Illegal JSON is warned about and ignored. The source file is never modified.
    """
    source = source_path if source_path is not None else Path.home() / ".claude.json"
    if not source.is_file():
        return
    try:
        source_document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning("Skipping Claude MCP merge; invalid source %s: %s", source, exc)
        return
    if not isinstance(source_document, dict):
        logger.warning("Skipping Claude MCP merge; source root is not an object: %s", source)
        return
    user_servers = source_document.get(CLAUDE_MCP_KEY, {})
    if user_servers is None:
        user_servers = {}
    if not isinstance(user_servers, dict):
        logger.warning("Skipping Claude MCP merge; mcpServers is not an object: %s", source)
        return

    target = state_home / ".claude.json"
    existing_document: dict[str, Any]
    existing_servers: dict[str, Any]
    if not target.exists():
        existing_document = {}
        existing_servers = {}
    else:
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.warning("Skipping Claude MCP merge; invalid target %s: %s", target, exc)
            return
        if not isinstance(loaded, dict):
            logger.warning("Skipping Claude MCP merge; target root is not an object: %s", target)
            return
        existing_document = loaded
        current = existing_document.get(CLAUDE_MCP_KEY, {})
        if current is None:
            current = {}
        if not isinstance(current, dict):
            logger.warning(
                "Skipping Claude MCP merge; target mcpServers is not an object: %s", target
            )
            return
        existing_servers = current

    merged_servers = {**existing_servers, **user_servers}
    if merged_servers == existing_servers and CLAUDE_MCP_KEY in existing_document:
        return

    output = dict(existing_document)
    output[CLAUDE_MCP_KEY] = merged_servers
    try:
        _write_json_atomic(target, output)
    except OSError as exc:
        logger.warning("Failed to write Claude MCP merge to %s: %s", target, exc)


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
