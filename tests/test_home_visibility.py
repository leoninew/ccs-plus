from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest
import tomlkit

from ccs_plus.domain import AppKind, ClaudeRuntime, CodexRuntime, GrokRuntime, Provider
from ccs_plus.home_visibility import (
    ClaudeHomeVisibility,
    CodexHomeVisibility,
    DisabledHomeVisibility,
    GrokHomeVisibility,
    _is_link,
    _links_to,
    home_visibility_for,
    link_user_entries,
)
from ccs_plus.settings import EntryVisibilitySettings

_CODEX_PROFILE_EXTENSION_KEYS = (
    "mcp_servers",
    "plugins",
    "marketplaces",
    "shell_environment_policy",
)
_GROK_EXTENSION_KEYS = ("mcp_servers", "skills", "plugins", "marketplace", "hooks")
_CODEX_SKILLS = EntryVisibilitySettings(skip_names=(".system",))
_CODEX_PLUGINS = EntryVisibilitySettings(
    skip_names=("cache", ".plugin-appserver", ".remote-plugin-install-staging")
)
_GROK_HOOKS = EntryVisibilitySettings(copy_names=("orca-status.json",))
_GROK_INSTALLED_PLUGINS = EntryVisibilitySettings(copy_names=("registry.json",))


def _runtime(runtime_type, app: AppKind):
    provider = Provider(
        id=f"{app.value}-official",
        app=app,
        name=app.value,
        settings_config={},
        endpoints=(),
        category="official",
        created_at=None,
        notes=None,
        is_current=False,
    )
    return runtime_type(
        provider=provider,
        endpoint=None,
        api_key=None,
        model=None,
        effort=None,
    )


def test_home_visibility_factory_selects_runtime_implementation(
    tmp_path: Path,
    app_settings,
) -> None:
    settings = app_settings(tmp_path)

    claude = home_visibility_for(_runtime(ClaudeRuntime, AppKind.CLAUDE), settings, tmp_path)
    codex = home_visibility_for(_runtime(CodexRuntime, AppKind.CODEX), settings, tmp_path)
    grok = home_visibility_for(_runtime(GrokRuntime, AppKind.GROK), settings, tmp_path)

    assert isinstance(claude, ClaudeHomeVisibility)
    assert claude.mcp_key == settings.claude.visibility.mcp_key
    assert claude.plugins == settings.claude.visibility.plugins
    assert isinstance(codex, CodexHomeVisibility)
    assert codex.profile_extension_keys == settings.codex.visibility.profile_extension_keys
    assert codex.skills == settings.codex.visibility.skills
    assert isinstance(grok, GrokHomeVisibility)
    assert grok.extension_keys == settings.grok.visibility.extension_keys
    assert grok.hooks == settings.grok.visibility.hooks


def test_disabled_codex_visibility_keeps_profile_extension_policy(
    tmp_path: Path, app_settings
) -> None:
    settings = app_settings(tmp_path)

    visibility = home_visibility_for(
        _runtime(CodexRuntime, AppKind.CODEX),
        settings,
        tmp_path,
        enabled=False,
    )

    assert isinstance(visibility, DisabledHomeVisibility)
    assert visibility.profile_extension_keys == settings.codex.visibility.profile_extension_keys


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


def test_claude_home_visibility_uses_plugin_name_sets(tmp_path: Path) -> None:
    user_home = tmp_path / "user-claude"
    state_home = tmp_path / "state-claude"
    plugins = user_home / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "marketplaces").mkdir()
    (plugins / "installed_plugins.json").write_text('{"p": 1}\n', encoding="utf-8")
    (plugins / "plugin-catalog-cache.json").write_text("cache\n", encoding="utf-8")

    ClaudeHomeVisibility(
        state_home=state_home,
        user_home=user_home,
        mcp_key="mcpServers",
        plugins=EntryVisibilitySettings(
            copy_names=("installed_plugins.json",),
            skip_names=("plugin-catalog-cache.json",),
        ),
    ).apply()

    copied = state_home / "plugins" / "installed_plugins.json"
    assert copied.read_text(encoding="utf-8") == '{"p": 1}\n'
    assert not _is_link(copied)
    assert _is_link(state_home / "plugins" / "marketplaces")
    assert _links_to(state_home / "plugins" / "marketplaces", plugins / "marketplaces")
    assert not (state_home / "plugins" / "plugin-catalog-cache.json").exists()


def test_codex_home_visibility_skips_plugin_runtime_directories(tmp_path: Path) -> None:
    user_home = tmp_path / "user-codex"
    state_home = tmp_path / "state-codex"
    (user_home / "plugins" / "cache").mkdir(parents=True)
    (user_home / "plugins" / ".plugin-appserver").mkdir()
    (user_home / "plugins" / ".remote-plugin-install-staging").mkdir()

    CodexHomeVisibility(
        state_home,
        user_home,
        profile_extension_keys=_CODEX_PROFILE_EXTENSION_KEYS,
        skills=_CODEX_SKILLS,
        plugins=_CODEX_PLUGINS,
    ).apply()

    assert (state_home / "plugins" / "cache").is_dir()
    assert not _is_link(state_home / "plugins" / "cache")
    assert not (state_home / "plugins" / ".plugin-appserver").exists()
    assert not (state_home / "plugins" / ".remote-plugin-install-staging").exists()


def test_codex_home_visibility_prunes_unregistered_plugin_cache(tmp_path, caplog) -> None:
    user_home = tmp_path / "user-codex"
    cache = user_home / "plugins" / "cache" / "local-marketplace"
    (cache / "example-plugin" / "1.0.0").mkdir(parents=True)
    visibility = CodexHomeVisibility(
        tmp_path / "state-codex",
        user_home,
        profile_extension_keys=_CODEX_PROFILE_EXTENSION_KEYS,
        skills=_CODEX_SKILLS,
        plugins=_CODEX_PLUGINS,
    )

    with caplog.at_level(logging.INFO, logger="ccs_plus.home_visibility"):
        document = tomlkit.document()
        document["plugins"] = tomlkit.table()
        visibility.merge_into(document)

    assert not (cache / "example-plugin").exists()
    assert not cache.exists()
    assert "example-plugin@local-marketplace" in caplog.text
    assert "Removed unregistered" in caplog.text


def test_codex_home_visibility_keeps_registered_plugin_cache(tmp_path) -> None:
    user_home = tmp_path / "user-codex"
    cache = user_home / "plugins" / "cache" / "local-marketplace"
    (cache / "example-plugin" / "1.0.0").mkdir(parents=True)
    visibility = CodexHomeVisibility(
        tmp_path / "state-codex",
        user_home,
        profile_extension_keys=_CODEX_PROFILE_EXTENSION_KEYS,
        skills=_CODEX_SKILLS,
        plugins=_CODEX_PLUGINS,
    )
    document = tomlkit.document()
    plugins = tomlkit.table()
    plugin = tomlkit.table()
    plugin["enabled"] = True
    plugins["example-plugin@local-marketplace"] = plugin
    document["plugins"] = plugins

    visibility.merge_into(document)

    assert (cache / "example-plugin").is_dir()


def test_grok_home_visibility_exposes_extensions_and_config(tmp_path: Path) -> None:
    user_home = tmp_path / "user-grok"
    state_home = tmp_path / "state-grok"
    (user_home / "skills" / "skill-a").mkdir(parents=True)
    (user_home / "plugins" / "plugin-a").mkdir(parents=True)
    (user_home / "hooks" / "hook-a").mkdir(parents=True)
    (user_home / "hooks" / "orca-status.json").write_text(
        '{"hooks": {"SessionStart": []}}\n',
        encoding="utf-8",
    )
    installed = user_home / "installed-plugins"
    (installed / "plugin-a").mkdir(parents=True)
    (installed / "registry.json").write_text('{"plugin-a": {}}\n', encoding="utf-8")
    (user_home / "config.toml").write_text(
        """
[mcp_servers.user]
command = "user"

[plugins]
enabled = ["plugin-a"]

[marketplace]
official_marketplace_auto_installed = true
""",
        encoding="utf-8",
    )

    GrokHomeVisibility(
        state_home,
        user_home,
        extension_keys=_GROK_EXTENSION_KEYS,
        hooks=_GROK_HOOKS,
        installed_plugins=_GROK_INSTALLED_PLUGINS,
    ).apply()

    assert _is_link(state_home / "skills" / "skill-a")
    assert _is_link(state_home / "plugins" / "plugin-a")
    assert _is_link(state_home / "hooks" / "hook-a")
    hook_status = state_home / "hooks" / "orca-status.json"
    assert hook_status.read_text(encoding="utf-8") == '{"hooks": {"SessionStart": []}}\n'
    assert not _is_link(hook_status)
    assert _is_link(state_home / "installed-plugins" / "plugin-a")
    registry = state_home / "installed-plugins" / "registry.json"
    assert registry.read_text(encoding="utf-8") == '{"plugin-a": {}}\n'
    assert not _is_link(registry)
    document = tomlkit.parse((state_home / "config.toml").read_text(encoding="utf-8"))
    assert document["mcp_servers"]["user"]["command"] == "user"
    assert document["plugins"]["enabled"] == ["plugin-a"]
    assert document["marketplace"]["official_marketplace_auto_installed"] is True


def test_grok_home_visibility_preserves_state_extension_keys(tmp_path: Path) -> None:
    user_home = tmp_path / "user-grok"
    state_home = tmp_path / "state-grok"
    user_home.mkdir()
    state_home.mkdir()
    (state_home / "config.toml").write_text(
        """
[plugins]
state_only = true
shared = "state"

[marketplace]
state_only = true
shared = "state"

[hooks]
state_only = true
shared = "state"
""",
        encoding="utf-8",
    )
    (user_home / "config.toml").write_text(
        """
[plugins]
user_only = true
shared = "user"

[marketplace]
user_only = true
shared = "user"

[hooks]
user_only = true
shared = "user"
""",
        encoding="utf-8",
    )

    GrokHomeVisibility(
        state_home,
        user_home,
        extension_keys=_GROK_EXTENSION_KEYS,
        hooks=_GROK_HOOKS,
        installed_plugins=_GROK_INSTALLED_PLUGINS,
    ).apply()
    document = tomlkit.parse((state_home / "config.toml").read_text(encoding="utf-8"))

    for key in ("plugins", "marketplace", "hooks"):
        assert document[key]["state_only"] is True
        assert document[key]["user_only"] is True
        assert document[key]["shared"] == "user"


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


def test_codex_home_visibility_links_only_the_session_directory(tmp_path: Path) -> None:
    user_home = tmp_path / "user-codex"
    state_home = tmp_path / "state-codex"

    CodexHomeVisibility(state_home, user_home).expose_sessions()

    source = user_home / "sessions"
    target = state_home / "sessions"
    assert source.is_dir()
    assert target.is_dir()
    assert _is_link(target)
    assert _links_to(target, source)
    assert not _is_link(state_home)
    (target / "created-by-runtime.jsonl").write_text("session", encoding="utf-8")
    assert (source / "created-by-runtime.jsonl").read_text(encoding="utf-8") == "session"


def test_codex_home_visibility_preserves_existing_session_directory(tmp_path: Path) -> None:
    user_home = tmp_path / "user-codex"
    state_home = tmp_path / "state-codex"
    existing = state_home / "sessions"
    existing.mkdir(parents=True)
    marker = existing / "keep.jsonl"
    marker.write_text("state", encoding="utf-8")

    CodexHomeVisibility(state_home, user_home).expose_sessions()

    assert marker.read_text(encoding="utf-8") == "state"
    assert not _is_link(existing)


def test_claude_home_visibility_merges_user_mcp_over_existing(tmp_path: Path) -> None:
    source = tmp_path / ".claude.json"
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

    ClaudeHomeVisibility(state, tmp_path / ".claude", mcp_key="mcpServers").apply()

    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["theme"] == "dark"
    assert document["mcpServers"] == {
        "shared": {"command": "user-shared"},
        "state-only": {"command": "state"},
        "user-only": {"command": "user"},
    }
    assert "user-only" in json.loads(source.read_text(encoding="utf-8"))["mcpServers"]


def test_claude_home_visibility_uses_configured_mcp_key(tmp_path: Path) -> None:
    source = tmp_path / ".claude.json"
    source.write_text('{"customMcp": {"user": {"command": "user"}}}\n', encoding="utf-8")
    state = tmp_path / "claude"

    ClaudeHomeVisibility(state, tmp_path / ".claude", mcp_key="customMcp").apply()

    document = json.loads((state / ".claude.json").read_text(encoding="utf-8"))
    assert document == {"customMcp": {"user": {"command": "user"}}}


def test_grok_home_visibility_merges_only_configured_extension_keys(tmp_path: Path) -> None:
    user_home = tmp_path / "user-grok"
    user_home.mkdir()
    (user_home / "config.toml").write_text(
        """
[mcp_servers.hidden]
command = "hidden"

[custom_extensions.visible]
command = "visible"
""",
        encoding="utf-8",
    )
    state_home = tmp_path / "state-grok"

    GrokHomeVisibility(
        state_home,
        user_home,
        extension_keys=("custom_extensions",),
    ).apply()

    document = tomlkit.parse((state_home / "config.toml").read_text(encoding="utf-8"))
    assert document["custom_extensions"]["visible"]["command"] == "visible"
    assert "mcp_servers" not in document


def test_claude_home_visibility_ignores_invalid_json(tmp_path: Path, caplog) -> None:
    source = tmp_path / ".claude.json"
    source.write_text("{not-json", encoding="utf-8")
    state = tmp_path / "claude"
    state.mkdir()
    target = state / ".claude.json"
    target.write_text('{"mcpServers": {"keep": {}}}\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="ccs_plus.home_visibility"):
        ClaudeHomeVisibility(state, tmp_path / ".claude", mcp_key="mcpServers").apply()

    assert "Skipping Claude MCP source" in caplog.text
    assert json.loads(target.read_text(encoding="utf-8")) == {"mcpServers": {"keep": {}}}


def test_claude_home_visibility_ignores_invalid_target(tmp_path: Path, caplog) -> None:
    source = tmp_path / ".claude.json"
    source.write_text(json.dumps({"mcpServers": {"a": {}}}), encoding="utf-8")
    state = tmp_path / "claude"
    state.mkdir()
    target = state / ".claude.json"
    target.write_text("{broken", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="ccs_plus.home_visibility"):
        ClaudeHomeVisibility(state, tmp_path / ".claude", mcp_key="mcpServers").apply()

    assert "Skipping Claude MCP target" in caplog.text
    assert target.read_text(encoding="utf-8") == "{broken"
