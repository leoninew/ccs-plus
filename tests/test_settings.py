from __future__ import annotations

from ccs_plus.settings import load_settings


def test_settings_default_homes_use_local_data(settings_root) -> None:
    settings = load_settings(settings_root)
    assert settings.claude_home == settings_root / "data" / "claude"
    assert settings.codex_home == settings_root / "data" / "codex"
    assert settings.grok_home == settings_root / "data" / "grok"


def test_environment_overrides_dynaconf_settings(settings_root, monkeypatch) -> None:
    monkeypatch.setenv("CCS_PLUS_CODEX_HOME", "custom/codex")
    settings = load_settings(settings_root)
    assert settings.codex_home == settings_root / "custom" / "codex"


def test_secrets_toml_is_not_loaded(settings_root) -> None:
    (settings_root / ".secrets.toml").write_text(
        '[default]\ndatabase_path = "should-not-be-used.db"\n', encoding="utf-8"
    )
    settings = load_settings(settings_root)
    assert settings.database_path.name == "cc-switch.db"
