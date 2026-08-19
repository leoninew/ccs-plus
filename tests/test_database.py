from __future__ import annotations

import sqlite3

import pytest

from ccs_plus.adapters import build_provider
from ccs_plus.database import ProviderRepository
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, ProviderError

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _new_provider(app: AppKind = AppKind.CODEX):
    return build_provider(
        NewProvider(
            app=app,
            name="Example",
            endpoint="https://api.example.test/v1",
            api_key="secret-value",
            model="example-model",
            effort="high" if app is AppKind.CODEX else None,
            notes="test provider",
        ),
        _CODEX,
    )


def test_add_list_and_delete_cascades_endpoints(database_path) -> None:
    repository = ProviderRepository(database_path)
    provider = _new_provider()
    repository.add(provider)

    found = repository.get(AppKind.CODEX, provider.id)
    assert found.name == "Example"
    assert found.endpoints == ("https://api.example.test/v1",)
    assert found.is_current is False

    repository.delete(AppKind.CODEX, provider.id)
    with sqlite3.connect(database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_endpoints").fetchone()[0] == 0
    with pytest.raises(ProviderError, match="not found"):
        repository.get(AppKind.CODEX, provider.id)


def test_get_by_name_resolves_synthetic_opencode_official(database_path) -> None:
    provider = ProviderRepository(database_path).get_by_name(
        AppKind.OPENCODE, " opencode official "
    )

    assert provider.id == "opencode-official"
    assert provider.is_official is True


def test_list_stored_keeps_insertion_order_while_list_re_sorts(database_path) -> None:
    repository = ProviderRepository(database_path)
    codex = _new_provider(AppKind.CODEX)
    claude = _new_provider(AppKind.CLAUDE)
    repository.add(codex)
    repository.add(claude)

    # list_stored() follows the physical (rowid) order in which rows were added.
    assert [provider.id for provider in repository.list_stored()] == [codex.id, claude.id]
    # list() re-sorts by app_type, so claude surfaces before codex; synthetic
    # OpenCode official is appended when missing from the database.
    assert [provider.id for provider in repository.list()] == [
        claude.id,
        codex.id,
        "opencode-official",
    ]


def test_add_many_rolls_back_when_a_later_provider_conflicts(database_path) -> None:
    repository = ProviderRepository(database_path)
    existing = _new_provider()
    imported = _new_provider()
    repository.add(existing)

    with pytest.raises(ProviderError, match="already exists"):
        repository.add_many((imported, existing))

    assert [provider.id for provider in repository.list()] == [existing.id, "opencode-official"]


def test_delete_rejects_official_provider(database_path) -> None:
    repository = ProviderRepository(database_path)
    provider = _new_provider(AppKind.CLAUDE)
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            INSERT INTO providers (id, app_type, name, settings_config, category, meta, is_current,
                                   in_failover_queue, cost_multiplier)
            VALUES (?, ?, ?, ?, 'official', '{}', 0, 0, '1.0')
            """,
            ("claude-official", "claude", provider.name, "{}"),
        )
    with pytest.raises(ProviderError, match="Official"):
        repository.delete(AppKind.CLAUDE, "claude-official")


def test_reset_non_official_deletes_only_custom_providers(database_path) -> None:
    repository = ProviderRepository(database_path)
    claude = _new_provider(AppKind.CLAUDE)
    codex = _new_provider(AppKind.CODEX)
    repository.add(claude)
    repository.add(codex)
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            INSERT INTO providers (id, app_type, name, settings_config, category, meta, is_current,
                                   in_failover_queue, cost_multiplier)
            VALUES (?, ?, ?, ?, 'official', '{}', 0, 0, '1.0')
            """,
            ("claude-official", "claude", "Claude", "{}"),
        )

    assert repository.reset_non_official([AppKind.CLAUDE]) == 1
    assert [provider.id for provider in repository.list()] == [
        "claude-official",
        codex.id,
        "opencode-official",
    ]
    with sqlite3.connect(database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_endpoints").fetchone()[0] == 1


def test_delete_is_scoped_by_app_type(database_path) -> None:
    repository = ProviderRepository(database_path)
    first = _new_provider(AppKind.CLAUDE)
    second = _new_provider(AppKind.CODEX)
    second = second.__class__(
        id=first.id,
        app=second.app,
        name=second.name,
        settings_config=second.settings_config,
        endpoints=second.endpoints,
        category=second.category,
        created_at=second.created_at,
        notes=second.notes,
        is_current=second.is_current,
        meta=second.meta,
    )
    repository.add(first)
    repository.add(second)

    repository.delete(AppKind.CLAUDE, first.id)
    assert repository.get(AppKind.CODEX, first.id).name == "Example"


def test_find_by_name_returns_matches_from_multiple_apps(database_path) -> None:
    repository = ProviderRepository(database_path)
    claude = _new_provider(AppKind.CLAUDE)
    codex = _new_provider(AppKind.CODEX)
    codex = codex.__class__(
        id=codex.id,
        app=codex.app,
        name=claude.name,
        settings_config=codex.settings_config,
        endpoints=codex.endpoints,
        category=codex.category,
        created_at=codex.created_at,
        notes=codex.notes,
        is_current=codex.is_current,
        meta=codex.meta,
    )
    repository.add(claude)
    repository.add(codex)

    found = repository.find_by_name("example")

    assert [provider.app for provider in found] == [AppKind.CLAUDE, AppKind.CODEX]


def test_get_by_name_is_scoped_to_app_type(database_path) -> None:
    repository = ProviderRepository(database_path)
    claude = _new_provider(AppKind.CLAUDE)
    codex = _new_provider(AppKind.CODEX)
    codex = codex.__class__(
        id=codex.id,
        app=codex.app,
        name=claude.name,
        settings_config=codex.settings_config,
        endpoints=codex.endpoints,
        category=codex.category,
        created_at=codex.created_at,
        notes=codex.notes,
        is_current=codex.is_current,
        meta=codex.meta,
    )
    repository.add(claude)
    repository.add(codex)

    found = repository.get_by_name(AppKind.CODEX, "example")

    assert found.id == codex.id
