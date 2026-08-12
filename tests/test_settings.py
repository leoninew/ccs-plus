from __future__ import annotations

from pathlib import Path

import pytest

from ccs_plus.domain import ProviderError
from ccs_plus.settings import load_settings


def test_settings_default_homes_use_local_data(settings_root) -> None:
    settings = load_settings(settings_root)
    assert settings.claude.home == settings_root / "data" / "claude"
    assert settings.codex.home == settings_root / "data" / "codex"
    assert settings.codex.session_model_provider == "ccs-plus-managed"
    assert settings.grok.home == settings_root / "data" / "grok"
    assert settings.state_home("codex") == settings.codex.home
    # user_home is not in settings.yaml; defaults to Path.home() / ".claude"|".codex"
    assert settings.claude.user_home == Path.home() / ".claude"
    assert settings.codex.user_home == Path.home() / ".codex"
    assert settings.grok.user_home is None


def test_settings_loads_codex_provider_defaults(settings_root) -> None:
    settings = load_settings(settings_root)
    assert settings.codex.approval_policy == "never"
    assert settings.codex.sandbox_mode == "danger-full-access"
    defaults = settings.codex.provider_defaults()
    assert defaults.approval_policy == "never"
    assert defaults.sandbox_mode == "danger-full-access"


def test_environment_overrides_nested_settings(settings_root, monkeypatch) -> None:
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__HOME", "custom/codex")
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__USER_HOME", "custom/user-codex")
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__SESSION_MODEL_PROVIDER", "shared-custom")
    monkeypatch.setenv("CCS_PLUS_APPS__CLAUDE__USER_HOME", "custom/user-claude")
    monkeypatch.setenv("CCS_PLUS_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    settings = load_settings(settings_root)
    assert settings.codex.home == settings_root / "custom" / "codex"
    assert settings.codex.user_home == settings_root / "custom" / "user-codex"
    assert settings.codex.session_model_provider == "shared-custom"
    assert settings.claude.user_home == settings_root / "custom" / "user-claude"
    assert settings.encryption_key == "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def test_yaml_user_home_override_when_explicitly_provided(settings_root) -> None:
    (settings_root / "settings.yaml").write_text(
        "\n".join(
            [
                "database:",
                '  path: "cc-switch.db"',
                'encryption_key: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="',
                "apps:",
                "  claude:",
                "    home: data/claude",
                "    user_home: custom/claude-user",
                "  codex:",
                "    home: data/codex",
                "    user_home: custom/codex-user",
                "    session_model_provider: ccs-plus-managed",
                "    approval_policy: never",
                "    sandbox_mode: danger-full-access",
                "  grok:",
                "    home: data/grok",
                "",
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(settings_root)
    assert settings.claude.user_home == settings_root / "custom" / "claude-user"
    assert settings.codex.user_home == settings_root / "custom" / "codex-user"


def test_blank_user_home_keeps_builtin_default(settings_root, monkeypatch) -> None:
    monkeypatch.setenv("CCS_PLUS_APPS__CLAUDE__USER_HOME", "   ")
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__USER_HOME", "")
    settings = load_settings(settings_root)
    assert settings.claude.user_home == Path.home() / ".claude"
    assert settings.codex.user_home == Path.home() / ".codex"


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
    (settings_root / "settings.yaml").write_text(
        "\n".join(
            [
                "database:",
                '  path: "cc-switch.db"',
                'encryption_key: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="',
                "apps:",
                "  claude:",
                "    home: data/claude",
                "  codex:",
                "    home: data/codex",
                "    session_model_provider: ccs-plus-managed",
                "  grok:",
                "    home: data/grok",
                "",
            ]
        ),
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
