from __future__ import annotations

from pathlib import Path

import pytest

from ccs_plus.domain import ProviderError
from ccs_plus.settings import load_settings


def test_settings_default_homes_use_local_data(settings_root) -> None:
    settings = load_settings(settings_root)
    assert settings.proxy == ""
    assert settings.claude.home == settings_root / "data" / "claude"
    assert settings.claude.permission_mode == "bypassPermissions"
    assert settings.codex.home == settings_root / "data" / "codex"
    assert settings.codex.session_model_provider == "ccs-plus-managed"
    assert settings.grok.sandbox_mode == "workspace"
    assert settings.grok.always_approve is True
    assert settings.grok.home == settings_root / "data" / "grok"
    assert settings.opencode.home == settings_root / "data" / "opencode"
    assert settings.opencode.permission_mode == "allow"
    assert settings.opencode.always_approve is False
    assert settings.state_home("codex") == settings.codex.home
    assert settings.state_home("opencode") == settings.opencode.home
    # user_home is not in settings.yaml; defaults to Path.home() / ".claude"|".codex"
    assert settings.claude.user_home == Path.home() / ".claude"
    assert settings.codex.user_home == Path.home() / ".codex"
    assert settings.grok.user_home == Path.home() / ".grok"
    assert settings.opencode.user_home == Path.home() / ".config" / "opencode"
    assert settings.opencode.user_data_home == Path.home() / ".local" / "share" / "opencode"
    assert settings.claude.visibility.mcp_key == "mcpServers"
    assert settings.claude.visibility.plugins.copy_names == (
        ".last_inuse_sweep",
        "blocklist.json",
        "installed_plugins.json",
        "known_marketplaces.json",
    )
    assert settings.codex.visibility.profile_extension_keys == (
        "mcp_servers",
        "plugins",
        "marketplaces",
        "shell_environment_policy",
    )
    assert settings.codex.visibility.skills.skip_names == (".system",)
    assert settings.grok.visibility.extension_keys == (
        "mcp_servers",
        "skills",
        "plugins",
        "marketplace",
        "hooks",
    )


def test_settings_loads_codex_provider_defaults(settings_root) -> None:
    settings = load_settings(settings_root)
    assert settings.codex.approval_policy == "never"
    assert settings.codex.sandbox_mode == "danger-full-access"
    defaults = settings.codex.provider_defaults()
    assert defaults.approval_policy == "never"
    assert defaults.sandbox_mode == "danger-full-access"


def test_environment_overrides_nested_settings(settings_root, monkeypatch) -> None:
    monkeypatch.setenv("CCS_PLUS_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__HOME", "custom/codex")
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__USER_HOME", "custom/user-codex")
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__SESSION_MODEL_PROVIDER", "shared-custom")
    monkeypatch.setenv("CCS_PLUS_APPS__CLAUDE__PERMISSION_MODE", "manual")
    monkeypatch.setenv("CCS_PLUS_APPS__CLAUDE__VISIBILITY__MCP_KEY", "customMcp")
    monkeypatch.setenv("CCS_PLUS_APPS__GROK__SANDBOX_MODE", "restricted")
    monkeypatch.setenv("CCS_PLUS_APPS__GROK__ALWAYS_APPROVE", "false")
    monkeypatch.setenv("CCS_PLUS_APPS__GROK__USER_HOME", "custom/user-grok")
    monkeypatch.setenv("CCS_PLUS_APPS__CLAUDE__USER_HOME", "custom/user-claude")
    monkeypatch.setenv("CCS_PLUS_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    settings = load_settings(settings_root)
    assert settings.codex.home == settings_root / "custom" / "codex"
    assert settings.proxy == "http://127.0.0.1:7890"
    assert settings.codex.user_home == settings_root / "custom" / "user-codex"
    assert settings.codex.session_model_provider == "shared-custom"
    assert settings.claude.permission_mode == "manual"
    assert settings.claude.visibility.mcp_key == "customMcp"
    assert settings.grok.sandbox_mode == "restricted"
    assert settings.grok.always_approve is False
    assert settings.grok.user_home == settings_root / "custom" / "user-grok"
    assert settings.claude.user_home == settings_root / "custom" / "user-claude"
    assert settings.encryption_key == "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def test_empty_proxy_environment_override_clears_yaml_value(settings_root, monkeypatch) -> None:
    path = settings_root / "settings.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace('proxy: ""', "proxy: http://yaml-proxy:7890"),
        encoding="utf-8",
    )
    monkeypatch.setenv("CCS_PLUS_PROXY", "")

    assert load_settings(settings_root).proxy == ""


def test_yaml_user_home_override_when_explicitly_provided(settings_root) -> None:
    path = settings_root / "settings.yaml"
    yaml = path.read_text(encoding="utf-8")
    path.write_text(
        yaml.replace(
            "    home: data/claude\n",
            "    home: data/claude\n    user_home: custom/claude-user\n",
        )
        .replace(
            "    home: data/codex\n",
            "    home: data/codex\n    user_home: custom/codex-user\n",
        )
        .replace(
            "    home: data/grok\n",
            "    home: data/grok\n    user_home: custom/grok-user\n",
        )
        .replace(
            "    home: data/opencode\n",
            "    home: data/opencode\n    user_home: custom/opencode-user\n",
        ),
        encoding="utf-8",
    )
    settings = load_settings(settings_root)
    assert settings.proxy == ""
    assert settings.claude.user_home == settings_root / "custom" / "claude-user"
    assert settings.codex.user_home == settings_root / "custom" / "codex-user"
    assert settings.grok.user_home == settings_root / "custom" / "grok-user"
    assert settings.opencode.user_home == settings_root / "custom" / "opencode-user"


def test_blank_user_home_keeps_builtin_default(settings_root, monkeypatch) -> None:
    monkeypatch.setenv("CCS_PLUS_APPS__CLAUDE__USER_HOME", "   ")
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__USER_HOME", "")
    monkeypatch.setenv("CCS_PLUS_APPS__GROK__USER_HOME", "  ")
    settings = load_settings(settings_root)
    assert settings.claude.user_home == Path.home() / ".claude"
    assert settings.codex.user_home == Path.home() / ".codex"
    assert settings.grok.user_home == Path.home() / ".grok"


def _replace_claude_visibility_plugins(settings_root: Path, plugins_block: str) -> None:
    path = settings_root / "settings.yaml"
    yaml = path.read_text(encoding="utf-8")
    path.write_text(
        yaml.replace(
            "      plugins:\n        copy:\n          - .last_inuse_sweep\n"
            "          - blocklist.json\n"
            "          - installed_plugins.json\n          - known_marketplaces.json\n"
            "        skip:\n          - plugin-catalog-cache.json\n",
            plugins_block,
        ),
        encoding="utf-8",
    )


def test_settings_claude_plugin_name_sets_from_yaml(settings_root) -> None:
    _replace_claude_visibility_plugins(
        settings_root,
        "      plugins:\n"
        "        copy:\n"
        "          - a.json\n"
        "          - b.json\n"
        "        skip:\n"
        "          - c.json\n",
    )

    settings = load_settings(settings_root)

    assert settings.claude.visibility.plugins.copy_names == ("a.json", "b.json")
    assert settings.claude.visibility.plugins.skip_names == ("c.json",)


def test_settings_claude_empty_plugin_names_are_honored(settings_root) -> None:
    _replace_claude_visibility_plugins(
        settings_root,
        "      plugins:\n        copy: []\n        skip: []\n",
    )

    settings = load_settings(settings_root)

    assert settings.claude.visibility.plugins.copy_names == ()
    assert settings.claude.visibility.plugins.skip_names == ()


def test_settings_rejects_non_list_plugin_names(settings_root) -> None:
    _replace_claude_visibility_plugins(
        settings_root,
        "      plugins:\n        copy: not-a-list\n",
    )

    with pytest.raises(ProviderError, match=r"apps\.claude\.visibility\.plugins\.copy"):
        load_settings(settings_root)


def test_settings_requires_cli_visibility_keys(settings_root) -> None:
    path = settings_root / "settings.yaml"
    path.write_text(
        "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines() if "mcp_key:" not in line
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderError, match=r"apps\.claude\.visibility\.mcp_key"):
        load_settings(settings_root)


def test_secrets_file_is_not_loaded(settings_root) -> None:
    (settings_root / ".secrets.yaml").write_text(
        'database:\n  path: "should-not-be-used.db"\n', encoding="utf-8"
    )
    settings = load_settings(settings_root)
    assert settings.database_path.name == "cc-switch.db"


def test_settings_rejects_example_encryption_key(settings_root, monkeypatch) -> None:
    monkeypatch.setenv("CCS_PLUS_ENCRYPTION_KEY", "replace-with-a-fernet-key")

    with pytest.raises(ProviderError, match="replace the example key"):
        load_settings(settings_root)


def test_settings_rejects_missing_codex_defaults(settings_root) -> None:
    path = settings_root / "settings.yaml"
    path.write_text(
        "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if "approval_policy:" not in line
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ProviderError, match=r"apps\.codex\.approval_policy"):
        load_settings(settings_root)


def test_settings_rejects_missing_codex_session_model_provider(settings_root) -> None:
    lines = (settings_root / "settings.yaml").read_text(encoding="utf-8").splitlines()
    (settings_root / "settings.yaml").write_text(
        "\n".join(line for line in lines if "session_model_provider" not in line) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderError, match=r"apps\.codex\.session_model_provider"):
        load_settings(settings_root)


def test_settings_keeps_defaults_when_opencode_block_is_missing(settings_root) -> None:
    path = settings_root / "settings.yaml"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[: lines.index("  opencode:")]) + "\n", encoding="utf-8")

    settings = load_settings(settings_root)

    assert settings.opencode.home == settings_root / "data" / "opencode"
    assert settings.opencode.permission_mode == "allow"
    assert settings.opencode.always_approve is False
