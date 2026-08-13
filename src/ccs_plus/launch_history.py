from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from time import time

from ccs_plus.domain import AppKind, Provider

_HISTORY_VERSION = 1


@dataclass(frozen=True)
class ProviderUsage:
    launches: int = 0
    last_launched_at: int = 0


class LaunchHistory:
    """Persist launcher-only preferences without changing the cc-switch database."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._usages: dict[str, ProviderUsage] = {}
        self._last_provider_ids: dict[AppKind, str] = {}

    @classmethod
    def load(cls, path: Path) -> LaunchHistory:
        history = cls(path)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return history
        if not isinstance(document, dict) or document.get("version") != _HISTORY_VERSION:
            return history

        raw_usages = document.get("providers")
        if isinstance(raw_usages, dict):
            for key, value in raw_usages.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                launches = value.get("launches")
                last_launched_at = value.get("last_launched_at")
                if (
                    isinstance(launches, int)
                    and launches >= 0
                    and isinstance(last_launched_at, int)
                ):
                    history._usages[key] = ProviderUsage(launches, last_launched_at)

        raw_last_provider_ids = document.get("last_provider_ids")
        if isinstance(raw_last_provider_ids, dict):
            for app_name, provider_id in raw_last_provider_ids.items():
                if not isinstance(app_name, str) or not isinstance(provider_id, str):
                    continue
                try:
                    history._last_provider_ids[AppKind(app_name)] = provider_id
                except ValueError:
                    continue
        return history

    def ordered(self, app: AppKind, providers: Iterable[Provider]) -> list[Provider]:
        return sorted(
            providers,
            key=lambda provider: (
                -self.usage(provider).launches,
                -self.usage(provider).last_launched_at,
                provider.name.casefold(),
                provider.id,
            ),
        )

    def default_provider_id(self, app: AppKind, providers: Iterable[Provider]) -> str | None:
        provider_ids = {provider.id for provider in providers}
        last_provider_id = self._last_provider_ids.get(app)
        if last_provider_id in provider_ids:
            return last_provider_id
        return None

    def usage(self, provider: Provider) -> ProviderUsage:
        return self._usages.get(_provider_key(provider), ProviderUsage())

    def record_launch(self, provider: Provider) -> None:
        key = _provider_key(provider)
        usage = self._usages.get(key, ProviderUsage())
        self._usages[key] = ProviderUsage(usage.launches + 1, int(time() * 1000))
        self._last_provider_ids[provider.app] = provider.id
        self._write()

    def _write(self) -> None:
        document = {
            "version": _HISTORY_VERSION,
            "providers": {
                key: {"launches": usage.launches, "last_launched_at": usage.last_launched_at}
                for key, usage in self._usages.items()
            },
            "last_provider_ids": {
                app.value: provider_id for app, provider_id in self._last_provider_ids.items()
            },
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temporary_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(temporary_path, self.path)
        except OSError:
            # Launch history is a convenience; it must never prevent a native CLI launch.
            return


def _provider_key(provider: Provider) -> str:
    return f"{provider.app.value}:{provider.id}"
