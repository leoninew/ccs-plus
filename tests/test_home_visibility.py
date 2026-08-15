from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from ccs_plus.home_visibility import (
    _is_link,
    _links_to,
    apply_claude_visibility,
    link_codex_sessions,
    link_user_entries,
    sync_claude_mcp_servers,
)


def test_link_user_entries_links_each_child_not_the_parent(tmp_path: Path) -> None:
    source = tmp_path / "user" / "skills"
    target = tmp_path / "state" / "skills"
    (source / "pomelo-db").mkdir(parents=True)
    (source / "specflow").mkdir()
    (source / ".system").mkdir()

    link_user_entries(source, target, skip_names={".system"})

    assert (target / "pomelo-db").exists()
    assert (target / "specflow").exists()
    assert not (target / ".system").exists()
    assert _is_link(target / "pomelo-db")
    assert _links_to(target / "pomelo-db", source / "pomelo-db")
    assert not _is_link(target)


def test_link_user_entries_skips_real_same_name_entries(tmp_path: Path) -> None:
    source = tmp_path / "user" / "skills"
    target = tmp_path / "state" / "skills"
    (source / "owned").mkdir(parents=True)
    (source / "owned" / "from-user.txt").write_text("user", encoding="utf-8")
    (target / "owned").mkdir(parents=True)
    (target / "owned" / "from-state.txt").write_text("state", encoding="utf-8")

    link_user_entries(source, target)

    assert (target / "owned" / "from-state.txt").read_text(encoding="utf-8") == "state"
    assert not (target / "owned" / "from-user.txt").exists()
    assert not _is_link(target / "owned")


def test_link_user_entries_removes_dangling_links(tmp_path: Path) -> None:
    source = tmp_path / "user" / "skills"
    target = tmp_path / "state" / "skills"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    gone = tmp_path / "missing-skill"
    gone.mkdir()
    dangling = target / "gone"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(gone), str(dangling))
    else:
        dangling.symlink_to(gone, target_is_directory=True)
    gone.rmdir()

    link_user_entries(source, target)

    assert not dangling.exists()
    assert not os.path.lexists(dangling)


def test_link_user_entries_links_files(tmp_path: Path) -> None:
    source = tmp_path / "user" / "plugins"
    target = tmp_path / "state" / "plugins"
    source.mkdir(parents=True)
    payload = source / "known_marketplaces.json"
    payload.write_text('{"ok": true}\n', encoding="utf-8")

    link_user_entries(source, target)

    linked = target / "known_marketplaces.json"
    assert linked.is_file()
    assert linked.read_text(encoding="utf-8") == '{"ok": true}\n'
    # hardlink or symlink both acceptable
    assert linked.stat().st_nlink >= 1 or linked.is_symlink()


def test_link_user_entries_missing_source_is_noop(tmp_path: Path) -> None:
    target = tmp_path / "state" / "skills"
    link_user_entries(tmp_path / "missing", target)
    assert not target.exists()


def test_apply_claude_visibility_uses_plugin_name_sets(tmp_path: Path) -> None:
    user_home = tmp_path / "user-claude"
    state_home = tmp_path / "state-claude"
    plugins = user_home / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "marketplaces").mkdir()
    (plugins / "installed_plugins.json").write_text('{"p": 1}\n', encoding="utf-8")
    (plugins / "plugin-catalog-cache.json").write_text("cache\n", encoding="utf-8")

    apply_claude_visibility(
        state_home,
        user_home,
        plugin_copy_names={"installed_plugins.json"},
        plugin_skip_names={"plugin-catalog-cache.json"},
    )

    copied = state_home / "plugins" / "installed_plugins.json"
    assert copied.read_text(encoding="utf-8") == '{"p": 1}\n'
    assert not _is_link(copied)
    assert _is_link(state_home / "plugins" / "marketplaces")
    assert _links_to(state_home / "plugins" / "marketplaces", plugins / "marketplaces")
    assert not (state_home / "plugins" / "plugin-catalog-cache.json").exists()


def test_link_user_entries_copies_named_files(tmp_path: Path) -> None:
    source = tmp_path / "user" / "plugins"
    target = tmp_path / "state" / "plugins"
    (source / "cache").mkdir(parents=True)
    (source / "cache" / "plugin-code").write_text("code", encoding="utf-8")
    payload = source / "installed_plugins.json"
    payload.write_text('{"plugins": {}}\n', encoding="utf-8")

    link_user_entries(source, target, copy_names={"installed_plugins.json"})

    copied = target / "installed_plugins.json"
    assert copied.read_text(encoding="utf-8") == '{"plugins": {}}\n'
    assert not _is_link(copied)
    # directories still share through a link, not a copy
    assert _is_link(target / "cache")
    assert _links_to(target / "cache", source / "cache")


def test_link_user_entries_copy_overrides_stale_target(tmp_path: Path) -> None:
    source = tmp_path / "user" / "plugins"
    target = tmp_path / "state" / "plugins"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    payload = source / "known_marketplaces.json"
    payload.write_text('{"real": true}\n', encoding="utf-8")
    stale = target / "known_marketplaces.json"
    stale.write_text('{"stale": true}\n', encoding="utf-8")

    link_user_entries(source, target, copy_names={"known_marketplaces.json"})

    assert stale.read_text(encoding="utf-8") == '{"real": true}\n'
    assert not _is_link(stale)


def test_link_user_entries_skips_named_entries(tmp_path: Path) -> None:
    source = tmp_path / "user" / "plugins"
    target = tmp_path / "state" / "plugins"
    source.mkdir(parents=True)
    (source / "plugin-catalog-cache.json").write_text("cache", encoding="utf-8")
    target.mkdir(parents=True)
    own = target / "plugin-catalog-cache.json"
    own.write_text("isolated-own-cache", encoding="utf-8")

    link_user_entries(source, target, skip_names={"plugin-catalog-cache.json"})

    assert own.read_text(encoding="utf-8") == "isolated-own-cache"
    assert not _is_link(own)


@pytest.mark.skipif(os.name == "nt", reason="file symlinks need SeCreateSymbolicLinkPrivilege")
def test_link_user_entries_copy_keeps_existing_link(tmp_path: Path) -> None:
    source = tmp_path / "user" / "plugins"
    target = tmp_path / "state" / "plugins"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    payload = source / "installed_plugins.json"
    payload.write_text('{"ok": true}\n', encoding="utf-8")
    existing = target / "installed_plugins.json"
    existing.symlink_to(payload)

    link_user_entries(source, target, copy_names={"installed_plugins.json"})

    assert existing.is_symlink()
    assert _links_to(existing, payload)


def test_link_codex_sessions_links_only_the_session_directory(tmp_path: Path) -> None:
    user_home = tmp_path / "user-codex"
    state_home = tmp_path / "state-codex"

    link_codex_sessions(state_home, user_home)

    source = user_home / "sessions"
    target = state_home / "sessions"
    assert source.is_dir()
    assert target.is_dir()
    assert _is_link(target)
    assert _links_to(target, source)
    assert not _is_link(state_home)
    (target / "created-by-runtime.jsonl").write_text("session", encoding="utf-8")
    assert (source / "created-by-runtime.jsonl").read_text(encoding="utf-8") == "session"


def test_link_codex_sessions_preserves_existing_directory(tmp_path: Path) -> None:
    user_home = tmp_path / "user-codex"
    state_home = tmp_path / "state-codex"
    existing = state_home / "sessions"
    existing.mkdir(parents=True)
    marker = existing / "keep.jsonl"
    marker.write_text("state", encoding="utf-8")

    link_codex_sessions(state_home, user_home)

    assert marker.read_text(encoding="utf-8") == "state"
    assert not _is_link(existing)


def test_sync_claude_mcp_servers_merges_user_over_existing(tmp_path: Path) -> None:
    source = tmp_path / "user.claude.json"
    source.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "shared": {"command": "user-shared"},
                    "user-only": {"command": "user"},
                }
            }
        ),
        encoding="utf-8",
    )
    state = tmp_path / "claude"
    state.mkdir()
    target = state / ".claude.json"
    target.write_text(
        json.dumps(
            {
                "theme": "dark",
                "mcpServers": {
                    "shared": {"command": "state-shared"},
                    "state-only": {"command": "state"},
                },
            }
        ),
        encoding="utf-8",
    )

    sync_claude_mcp_servers(state, source_path=source)

    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["theme"] == "dark"
    assert document["mcpServers"] == {
        "shared": {"command": "user-shared"},
        "state-only": {"command": "state"},
        "user-only": {"command": "user"},
    }
    assert "user-only" in json.loads(source.read_text(encoding="utf-8"))["mcpServers"]


def test_sync_claude_mcp_servers_ignores_invalid_json(tmp_path: Path, caplog) -> None:
    source = tmp_path / "user.claude.json"
    source.write_text("{not-json", encoding="utf-8")
    state = tmp_path / "claude"
    state.mkdir()
    target = state / ".claude.json"
    target.write_text('{"mcpServers": {"keep": {}}}\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="ccs_plus.home_visibility"):
        sync_claude_mcp_servers(state, source_path=source)

    assert "Skipping Claude MCP merge" in caplog.text
    assert json.loads(target.read_text(encoding="utf-8")) == {"mcpServers": {"keep": {}}}


def test_sync_claude_mcp_servers_ignores_invalid_target(tmp_path: Path, caplog) -> None:
    source = tmp_path / "user.claude.json"
    source.write_text(json.dumps({"mcpServers": {"a": {}}}), encoding="utf-8")
    state = tmp_path / "claude"
    state.mkdir()
    target = state / ".claude.json"
    target.write_text("{broken", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="ccs_plus.home_visibility"):
        sync_claude_mcp_servers(state, source_path=source)

    assert "invalid target" in caplog.text
    assert target.read_text(encoding="utf-8") == "{broken"
