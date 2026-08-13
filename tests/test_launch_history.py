from __future__ import annotations

from dataclasses import replace

from ccs_plus.adapters import build_provider
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider
from ccs_plus.launch_history import LaunchHistory

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _provider(name: str):
    return build_provider(
        NewProvider(
            app=AppKind.CODEX,
            name=name,
            endpoint="https://api.example.test/v1",
            api_key="history-test-key",
            model="example-model",
            effort="high",
            notes=None,
        ),
        _CODEX,
    )


def test_history_orders_by_usage_and_remembers_last_provider(tmp_path) -> None:
    first = _provider("First")
    second = replace(_provider("Second"), created_at=first.created_at)
    path = tmp_path / "history.json"

    history = LaunchHistory.load(path)
    history.record_launch(second)
    history.record_launch(second)
    history.record_launch(first)

    reloaded = LaunchHistory.load(path)
    assert [provider.id for provider in reloaded.ordered(first.app, [first, second])] == [
        second.id,
        first.id,
    ]
    assert reloaded.default_provider_id(first.app, [first, second]) == first.id


def test_history_ignores_a_corrupt_file(tmp_path) -> None:
    path = tmp_path / "history.json"
    path.write_text("not json", encoding="utf-8")

    history = LaunchHistory.load(path)

    assert history.default_provider_id(AppKind.CODEX, []) is None
