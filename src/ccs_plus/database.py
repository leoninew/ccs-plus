from __future__ import annotations

import builtins
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from ccs_plus.domain import AppKind, Provider, ProviderError

REQUIRED_PROVIDER_COLUMNS = {
    "id",
    "app_type",
    "name",
    "settings_config",
    "category",
    "created_at",
    "notes",
    "meta",
    "is_current",
    "in_failover_queue",
}
REQUIRED_ENDPOINT_COLUMNS = {"provider_id", "app_type", "url", "added_at"}


class ProviderRepository:
    def __init__(self, database_path: Path, busy_timeout_ms: int = 5_000) -> None:
        self.database_path = database_path
        self.busy_timeout_ms = busy_timeout_ms

    def list(self, apps: Iterable[AppKind] | None = None) -> builtins.list[Provider]:
        selected = tuple(apps or AppKind)
        if not selected:
            return []
        conn = self._connect()
        try:
            self._preflight(conn)
            placeholders = ", ".join("?" for _ in selected)
            rows = conn.execute(
                f"""
                SELECT id, app_type, name, settings_config, category, created_at, notes, meta,
                       is_current
                FROM providers
                WHERE app_type IN ({placeholders})
                ORDER BY app_type, COALESCE(sort_index, 999999), created_at, id
                """,
                tuple(app.db_app_type for app in selected),
            ).fetchall()
            return [self._row_to_provider(conn, row) for row in rows]
        finally:
            conn.close()

    def get(self, app: AppKind, provider_id: str) -> Provider:
        conn = self._connect()
        try:
            self._preflight(conn)
            row = conn.execute(
                """
                SELECT id, app_type, name, settings_config, category, created_at, notes, meta,
                       is_current
                FROM providers
                WHERE id = ? AND app_type = ?
                """,
                (provider_id, app.db_app_type),
            ).fetchone()
            if row is None:
                raise ProviderError(f"Provider not found: {provider_id} ({app.value})")
            return self._row_to_provider(conn, row)
        finally:
            conn.close()

    def find_by_name(self, name: str) -> builtins.list[Provider]:
        normalized_name = name.strip()
        if not normalized_name:
            raise ProviderError("Provider name cannot be empty.")
        conn = self._connect()
        try:
            self._preflight(conn)
            rows = conn.execute(
                """
                SELECT id, app_type, name, settings_config, category, created_at, notes, meta,
                       is_current
                FROM providers
                WHERE name = ? COLLATE NOCASE
                ORDER BY app_type, COALESCE(sort_index, 999999), created_at, id
                """,
                (normalized_name,),
            ).fetchall()
            if not rows:
                raise ProviderError(f"Provider not found by name: {normalized_name}")
            return [self._row_to_provider(conn, row) for row in rows]
        finally:
            conn.close()

    def get_by_name(self, app: AppKind, name: str) -> Provider:
        normalized_name = name.strip()
        if not normalized_name:
            raise ProviderError("Provider name cannot be empty.")
        conn = self._connect()
        try:
            self._preflight(conn)
            rows = conn.execute(
                """
                SELECT id, app_type, name, settings_config, category, created_at, notes, meta,
                       is_current
                FROM providers
                WHERE app_type = ? AND name = ? COLLATE NOCASE
                ORDER BY COALESCE(sort_index, 999999), created_at, id
                """,
                (app.db_app_type, normalized_name),
            ).fetchall()
            if not rows:
                raise ProviderError(f"Provider not found: {normalized_name} ({app.value})")
            if len(rows) > 1:
                raise ProviderError(
                    f"Provider name is ambiguous for {app.value}: {normalized_name}. "
                    "Remove or rename duplicate providers before deleting."
                )
            return self._row_to_provider(conn, rows[0])
        finally:
            conn.close()

    def add(self, provider: Provider) -> None:
        if not provider.endpoints:
            raise ProviderError("A provider must have at least one endpoint.")
        conn = self._connect()
        try:
            self._preflight(conn)
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT 1 FROM providers WHERE id = ? AND app_type = ?",
                    (provider.id, provider.app.db_app_type),
                ).fetchone()
                if existing is not None:
                    raise ProviderError(f"Provider already exists: {provider.id}")

                conn.execute(
                    """
                    INSERT INTO providers (
                        id, app_type, name, settings_config, category, created_at, notes, meta,
                        is_current, in_failover_queue
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                    """,
                    (
                        provider.id,
                        provider.app.db_app_type,
                        provider.name,
                        json.dumps(provider.settings_config, ensure_ascii=False),
                        provider.category,
                        provider.created_at,
                        provider.notes,
                        json.dumps(provider.meta, ensure_ascii=False),
                    ),
                )
                for endpoint in provider.endpoints:
                    conn.execute(
                        """
                        INSERT INTO provider_endpoints (provider_id, app_type, url, added_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            provider.id,
                            provider.app.db_app_type,
                            endpoint,
                            provider.created_at,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        except sqlite3.Error as exc:
            raise ProviderError(f"Unable to add provider: {exc}") from exc
        finally:
            conn.close()

    def delete(self, app: AppKind, provider_id: str) -> None:
        conn = self._connect()
        try:
            self._preflight(conn)
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT id, app_type, name, settings_config, category, created_at, notes, meta,
                           is_current
                    FROM providers
                    WHERE id = ? AND app_type = ?
                    """,
                    (provider_id, app.db_app_type),
                ).fetchone()
                if row is None:
                    raise ProviderError(f"Provider not found: {provider_id} ({app.value})")
                provider = self._row_to_provider(conn, row)
                if provider.is_official:
                    raise ProviderError("Official providers cannot be deleted.")
                conn.execute(
                    "DELETE FROM providers WHERE id = ? AND app_type = ?",
                    (provider_id, app.db_app_type),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        except sqlite3.Error as exc:
            raise ProviderError(f"Unable to delete provider: {exc}") from exc
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise ProviderError(f"cc-switch database does not exist: {self.database_path}")
        try:
            conn = sqlite3.connect(self.database_path, timeout=self.busy_timeout_ms / 1000)
        except sqlite3.Error as exc:
            raise ProviderError(f"Unable to open cc-switch database: {exc}") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        return conn

    @staticmethod
    def _preflight(conn: sqlite3.Connection) -> None:
        provider_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(providers)").fetchall()
        }
        endpoint_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(provider_endpoints)").fetchall()
        }
        missing_providers = REQUIRED_PROVIDER_COLUMNS - provider_columns
        missing_endpoints = REQUIRED_ENDPOINT_COLUMNS - endpoint_columns
        if missing_providers or missing_endpoints:
            missing = sorted(missing_providers | missing_endpoints)
            raise ProviderError(
                f"Unsupported cc-switch database schema; missing columns: {', '.join(missing)}"
            )

    def _row_to_provider(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Provider:
        try:
            raw_settings = json.loads(row["settings_config"])
            settings = raw_settings if isinstance(raw_settings, dict) else {}
        except (TypeError, json.JSONDecodeError):
            settings = {}
        try:
            raw_meta = json.loads(row["meta"])
            meta = raw_meta if isinstance(raw_meta, dict) else {}
        except (TypeError, json.JSONDecodeError):
            meta = {}
        endpoints = tuple(
            item["url"]
            for item in conn.execute(
                """
                SELECT url FROM provider_endpoints
                WHERE provider_id = ? AND app_type = ?
                ORDER BY added_at, url
                """,
                (row["id"], row["app_type"]),
            ).fetchall()
        )
        app = AppKind.GROK if row["app_type"] == "grokbuild" else AppKind(row["app_type"])
        return Provider(
            id=row["id"],
            app=app,
            name=row["name"],
            settings_config=settings,
            endpoints=endpoints,
            category=row["category"],
            created_at=row["created_at"],
            notes=row["notes"],
            is_current=bool(row["is_current"]),
            meta=meta,
        )
