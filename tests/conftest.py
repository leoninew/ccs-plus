from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ccs_plus.domain import CodexAppConfig
from ccs_plus.settings import AppHomeSettings, AppSettings, CodexSettings


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "cc-switch.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE providers (
            id TEXT NOT NULL,
            app_type TEXT NOT NULL,
            name TEXT NOT NULL,
            settings_config TEXT NOT NULL,
            website_url TEXT,
            category TEXT,
            created_at INTEGER,
            sort_index INTEGER,
            notes TEXT,
            icon TEXT,
            icon_color TEXT,
            meta TEXT NOT NULL DEFAULT '{}',
            is_current BOOLEAN NOT NULL DEFAULT 0,
            in_failover_queue BOOLEAN NOT NULL DEFAULT 0,
            cost_multiplier TEXT NOT NULL DEFAULT '1.0',
            limit_daily_usd TEXT,
            limit_monthly_usd TEXT,
            provider_type TEXT,
            PRIMARY KEY (id, app_type)
        );
        CREATE TABLE provider_endpoints (
            id INTEGER PRIMARY KEY,
            provider_id TEXT NOT NULL,
            app_type TEXT NOT NULL,
            url TEXT NOT NULL,
            added_at INTEGER,
            FOREIGN KEY(provider_id, app_type) REFERENCES providers(id, app_type) ON DELETE CASCADE
        );
        """
    )
    conn.close()
    return path


@pytest.fixture()
def codex_app_config() -> CodexAppConfig:
    return CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def make_app_settings(
    root: Path,
    *,
    database_path: Path | None = None,
    encryption_key: str = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    approval_policy: str = "never",
    sandbox_mode: str = "danger-full-access",
    session_model_provider: str = "ccs-plus-managed",
    claude_user_home: Path | None = None,
    codex_user_home: Path | None = None,
) -> AppSettings:
    return AppSettings(
        project_root=root,
        database_path=database_path or (root / "cc-switch.db"),
        encryption_key=encryption_key,
        claude=AppHomeSettings(
            home=root / "claude",
            user_home=claude_user_home if claude_user_home is not None else root / "user-claude",
        ),
        codex=CodexSettings(
            home=root / "codex",
            user_home=codex_user_home if codex_user_home is not None else root / "user-codex",
            session_model_provider=session_model_provider,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
        ),
        grok=AppHomeSettings(home=root / "grok"),
    )


@pytest.fixture()
def app_settings():
    return make_app_settings


@pytest.fixture()
def settings_root(tmp_path: Path, database_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    (root / "settings.yaml").write_text(
        "\n".join(
            [
                "database:",
                f'  path: "{database_path.as_posix()}"',
                'encryption_key: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="',
                "apps:",
                "  claude:",
                "    home: data/claude",
                "  codex:",
                "    home: data/codex",
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
    return root
