from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


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
def settings_root(tmp_path: Path, database_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    (root / "settings.toml").write_text(
        "\n".join(
            [
                "[default]",
                f'database_path = "{database_path.as_posix()}"',
                'claude_home = "data/claude"',
                'codex_home = "data/codex"',
                'grok_home = "data/grok"',
                'encryption_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root
