from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ccs_plus.home_visibility import (
    _is_link,
    _links_to,
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
