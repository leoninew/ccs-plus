"""Pipe-input tests for the multi-pane launcher TUI."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from conftest import make_app_settings
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from ccs_plus.adapters import build_provider
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, Provider
from ccs_plus.launch_history import LaunchHistory
from ccs_plus.tui import APPROVAL_PRESETS, LaunchPlan, run_launcher

_T = TypeVar("_T")
_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _drive(func: Callable[[], _T], keys: str, *, delay: float = 0.35) -> _T:
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):

        def send() -> None:
            time.sleep(delay)
            pipe.send_text(keys)

        threading.Thread(target=send, daemon=True).start()
        return func()


def _provider(app: AppKind = AppKind.CLAUDE, name: str = "Example"):
    return build_provider(
        NewProvider(
            app=app,
            name=name,
            endpoint="https://api.example.test/v1",
            api_key="secret",
            model="model-a",
            effort="high" if app is not AppKind.GROK else None,
            notes=None,
        ),
        _CODEX,
    )


def _run(tmp_path: Path, providers, keys: str) -> LaunchPlan | None:
    settings = make_app_settings(tmp_path)
    history = LaunchHistory.load(tmp_path / "history.json")
    return _drive(
        lambda: run_launcher(
            settings=settings,
            providers=providers,
            history=history,
            default_cwd=tmp_path,
        ),
        keys,
    )


def test_launcher_escape_cancels(tmp_path: Path) -> None:
    assert _run(tmp_path, [_provider()], "\x1b") is None


def test_launcher_default_path_launches_new_session(tmp_path: Path) -> None:
    provider = _provider(AppKind.CLAUDE)
    # focus starts on app → enter → provider → enter → dir → enter
    # → sessions (new) → enter → buttons Launch → enter
    keys = "\r\r\r\r\r"
    plan = _run(tmp_path, [provider], keys)
    assert plan is not None
    assert plan.provider.id == provider.id
    assert plan.cwd == tmp_path.resolve()
    assert plan.session is None
    assert plan.approval_policy is None


def test_launcher_selects_codex_and_permission_preset(tmp_path: Path) -> None:
    claude = _provider(AppKind.CLAUDE, "Claude P")
    codex = _provider(AppKind.CODEX, "Codex P")
    # app: down to codex → enter → provider enter → dir enter
    # → permissions: down once (On request) → enter → sessions enter → Launch enter
    keys = "\x1b[B\r\r\r\x1b[B\r\r\r"
    plan = _run(tmp_path, [claude, codex], keys)
    assert plan is not None
    assert plan.provider.app is AppKind.CODEX
    assert plan.approval_policy == APPROVAL_PRESETS[1].approval_policy
    assert plan.sandbox_mode == APPROVAL_PRESETS[1].sandbox_mode


def test_codex_permission_presets_use_supported_approval_policies() -> None:
    assert {preset.approval_policy for preset in APPROVAL_PRESETS} <= {
        "never",
        "on-request",
        "on-failure",
    }


def test_launcher_keeps_provider_permissions_without_explicit_override(tmp_path: Path) -> None:
    provider = _provider(AppKind.CODEX, "Codex P")
    config = provider.settings_config["config"].replace(
        'approval_policy = "never"', 'approval_policy = "on-request"'
    )
    config = config.replace(
        'sandbox_mode = "danger-full-access"', 'sandbox_mode = "workspace-write"'
    )
    provider = Provider(
        **{
            **provider.__dict__,
            "settings_config": {**provider.settings_config, "config": config},
        }
    )

    # app → provider → dir → permissions → sessions → buttons → launch
    plan = _run(tmp_path, [provider], "\r\r\r\r\r\r")

    assert plan is not None
    assert plan.approval_policy is None
    assert plan.sandbox_mode is None


def test_launcher_resume_selects_session(tmp_path: Path) -> None:
    import json

    provider = _provider(AppKind.CODEX, "Codex P")
    settings = make_app_settings(tmp_path)
    day = settings.codex.user_home / "sessions" / "2026" / "08" / "13"
    day.mkdir(parents=True)
    session_cwd = tmp_path / "work"
    session_cwd.mkdir()
    sid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    (day / f"rollout-2026-08-13T12-00-00-{sid}.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": sid,
                            "timestamp": "2026-08-13T04:00:00.000Z",
                            "cwd": str(session_cwd),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "role": "user",
                            "content": [{"type": "input_text", "text": "resume me"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    history = LaunchHistory.load(tmp_path / "history.json")
    # app → provider → dir → permissions → sessions → down (resume) → launch
    # Directory pane hides after a session is selected; cwd comes from session.
    keys = "\r\r\r\r\x1b[B\r\r"
    plan = _drive(
        lambda: run_launcher(
            settings=settings,
            providers=[provider],
            history=history,
            default_cwd=tmp_path,
        ),
        keys,
        delay=0.4,
    )
    assert plan is not None
    assert plan.session is not None
    assert plan.session.session_id == sid
    assert plan.cwd == session_cwd.resolve()
