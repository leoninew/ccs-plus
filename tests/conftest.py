from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from ccs_plus.domain import CodexAppConfig
from ccs_plus.settings import (
    AppSettings,
    ClaudeSettings,
    ClaudeVisibilitySettings,
    CodexSettings,
    CodexVisibilitySettings,
    EntryVisibilitySettings,
    GrokSettings,
    GrokVisibilitySettings,
    OpenCodeSettings,
)


@pytest.fixture(autouse=True)
def _clean_ccs_plus_environment(monkeypatch) -> None:
    """Keep ambient CCS_PLUS_* variables out of settings tests.

    The developer shell may export e.g. CCS_PLUS_PROXY; Dynaconf's envvar_prefix
    would otherwise let it override settings.yaml values inside load_settings.
    Tests that want a value set it again via monkeypatch.setenv.
    """
    for key in [key for key in os.environ if key.startswith("CCS_PLUS_")]:
        monkeypatch.delenv(key, raising=False)


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
    proxy: str = "",
    approval_policy: str = "never",
    sandbox_mode: str = "danger-full-access",
    session_model_provider: str = "ccs-plus-managed",
    claude_permission_mode: str = "bypassPermissions",
    grok_sandbox_mode: str = "workspace",
    grok_always_approve: bool = True,
    opencode_permission_mode: str = "allow",
    opencode_always_approve: bool = False,
    claude_user_home: Path | None = None,
    codex_user_home: Path | None = None,
    grok_user_home: Path | None = None,
    opencode_user_home: Path | None = None,
    opencode_user_data_home: Path | None = None,
) -> AppSettings:
    return AppSettings(
        project_root=root,
        database_path=database_path or (root / "cc-switch.db"),
        encryption_key=encryption_key,
        proxy=proxy,
        claude=ClaudeSettings(
            home=root / "claude",
            user_home=claude_user_home if claude_user_home is not None else root / "user-claude",
            permission_mode=claude_permission_mode,
            visibility=ClaudeVisibilitySettings(
                mcp_key="mcpServers",
                skills=EntryVisibilitySettings(),
                plugins=EntryVisibilitySettings(),
            ),
        ),
        codex=CodexSettings(
            home=root / "codex",
            user_home=codex_user_home if codex_user_home is not None else root / "user-codex",
            session_model_provider=session_model_provider,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
            visibility=CodexVisibilitySettings(
                profile_extension_keys=(
                    "mcp_servers",
                    "plugins",
                    "marketplaces",
                    "shell_environment_policy",
                ),
                skills=EntryVisibilitySettings(skip_names=(".system",)),
                plugins=EntryVisibilitySettings(
                    skip_names=(".plugin-appserver", ".remote-plugin-install-staging")
                ),
            ),
        ),
        grok=GrokSettings(
            home=root / "grok",
            sandbox_mode=grok_sandbox_mode,
            always_approve=grok_always_approve,
            user_home=grok_user_home if grok_user_home is not None else root / "user-grok",
            visibility=GrokVisibilitySettings(
                extension_keys=("mcp_servers", "skills", "plugins", "marketplace", "hooks"),
                skills=EntryVisibilitySettings(),
                plugins=EntryVisibilitySettings(),
                hooks=EntryVisibilitySettings(copy_names=("orca-status.json",)),
                installed_plugins=EntryVisibilitySettings(copy_names=("registry.json",)),
            ),
        ),
        opencode=OpenCodeSettings(
            home=root / "opencode",
            permission_mode=opencode_permission_mode,
            always_approve=opencode_always_approve,
            user_home=(
                opencode_user_home if opencode_user_home is not None else root / "user-opencode"
            ),
            user_data_home=(
                opencode_user_data_home
                if opencode_user_data_home is not None
                else root / "user-opencode-data"
            ),
        ),
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
                'proxy: ""',
                "apps:",
                "  claude:",
                "    home: data/claude",
                "    permission_mode: bypassPermissions",
                "    visibility:",
                "      mcp_key: mcpServers",
                "      settings_keys:",
                "        - enabledPlugins",
                "        - extraKnownMarketplaces",
                "      skills: {}",
                "      plugins:",
                "        copy:",
                "          - .last_inuse_sweep",
                "          - blocklist.json",
                "          - installed_plugins.json",
                "          - known_marketplaces.json",
                "        skip:",
                "          - plugin-catalog-cache.json",
                "  codex:",
                "    home: data/codex",
                "    session_model_provider: ccs-plus-managed",
                "    approval_policy: never",
                "    sandbox_mode: danger-full-access",
                "    visibility:",
                "      profile_extension_keys:",
                "        - mcp_servers",
                "        - plugins",
                "        - marketplaces",
                "        - shell_environment_policy",
                "      skills:",
                "        skip:",
                "          - .system",
                "      plugins:",
                "        skip:",
                "          - .plugin-appserver",
                "          - .remote-plugin-install-staging",
                "  grok:",
                "    home: data/grok",
                "    sandbox_mode: workspace",
                "    always_approve: true",
                "    visibility:",
                "      extension_keys:",
                "        - mcp_servers",
                "        - skills",
                "        - plugins",
                "        - marketplace",
                "        - hooks",
                "      skills: {}",
                "      plugins: {}",
                "      hooks:",
                "        copy:",
                "          - orca-status.json",
                "      installed_plugins:",
                "        copy:",
                "          - registry.json",
                "  opencode:",
                "    home: data/opencode",
                "    permission_mode: allow",
                "    always_approve: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root
