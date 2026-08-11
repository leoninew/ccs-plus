from __future__ import annotations

import pytest

from ccs_plus.domain import ProviderError
from ccs_plus.settings import load_settings


def test_settings_default_homes_use_local_data(settings_root) -> None:
    settings = load_settings(settings_root)
    assert settings.claude.home == settings_root / "data" / "claude"
    assert settings.codex.home == settings_root / "data" / "codex"
    assert settings.grok.home == settings_root / "data" / "grok"
    assert settings.state_home("codex") == settings.codex.home


def test_settings_loads_codex_provider_defaults(settings_root) -> None:
    settings = load_settings(settings_root)
    assert settings.codex.approval_policy == "never"
    assert settings.codex.sandbox_mode == "danger-full-access"
    defaults = settings.codex.provider_defaults()
    assert defaults.approval_policy == "never"
    assert defaults.sandbox_mode == "danger-full-access"


def test_environment_overrides_nested_settings(settings_root, monkeypatch) -> None:
    monkeypatch.setenv("CCS_PLUS_APPS__CODEX__HOME", "custom/codex")
    monkeypatch.setenv("CCS_PLUS_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    settings = load_settings(settings_root)
    assert settings.codex.home == settings_root / "custom" / "codex"
    assert settings.encryption_key == "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


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
                "  grok:",
                "    home: data/grok",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProviderError, match=r"apps\.codex\.approval_policy"):
        load_settings(settings_root)
