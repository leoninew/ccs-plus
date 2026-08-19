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
from ccs_plus.tui import PERMISSION_PRESETS, LaunchPlan, run_launcher

_T = TypeVar("_T")
_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")

# app → provider → dir → permissions → sessions → buttons
_NEW_SESSION_KEYS = "\r\r\r\r\r\r"


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
    plan = _run(tmp_path, [provider], _NEW_SESSION_KEYS)
    assert plan is not None
    assert plan.provider.id == provider.id
    assert plan.cwd == tmp_path.resolve()
    assert plan.session is None
    assert plan.approval_policy is None
    assert plan.permission_mode is None
    assert plan.always_approve is None


def test_launcher_keeps_provider_list_order_instead_of_sorting_by_name(tmp_path: Path) -> None:
    first = _provider(AppKind.CLAUDE, "Zulu")
    second = _provider(AppKind.CLAUDE, "Alpha")

    plan = _run(tmp_path, [first, second], _NEW_SESSION_KEYS)

    assert plan is not None
    assert plan.provider.id == first.id


def test_launcher_selects_codex_and_permission_preset(tmp_path: Path) -> None:
    claude = _provider(AppKind.CLAUDE, "Claude P")
    codex = _provider(AppKind.CODEX, "Codex P")
    presets = PERMISSION_PRESETS[AppKind.CODEX]
    on_request = next(preset for preset in presets if preset.key == "on-request")
    # app: down to codex → enter → provider → dir
    # → permissions: down to On request (index 2) → sessions → Launch
    keys = "\x1b[B\r\r\r\x1b[B\x1b[B\r\r\r"
    plan = _run(tmp_path, [claude, codex], keys)
    assert plan is not None
    assert plan.provider.app is AppKind.CODEX
    assert plan.approval_policy == on_request.approval_policy
    assert plan.sandbox_mode == on_request.sandbox_mode


def test_permission_presets_match_native_cli_values() -> None:
    claude_modes = {preset.permission_mode for preset in PERMISSION_PRESETS[AppKind.CLAUDE]}
    assert claude_modes <= {
        "acceptEdits",
        "auto",
        "bypassPermissions",
        "manual",
        "dontAsk",
        "plan",
    }

    codex_approvals = {preset.approval_policy for preset in PERMISSION_PRESETS[AppKind.CODEX]}
    codex_sandboxes = {preset.sandbox_mode for preset in PERMISSION_PRESETS[AppKind.CODEX]}
    assert codex_approvals <= {"never", "on-request", "untrusted"}
    assert codex_sandboxes <= {"read-only", "workspace-write", "danger-full-access"}

    grok_sandboxes = {preset.sandbox_mode for preset in PERMISSION_PRESETS[AppKind.GROK]}
    assert grok_sandboxes <= {"off", "workspace", "devbox", "read-only", "strict"}
    assert all(
        isinstance(preset.always_approve, bool) for preset in PERMISSION_PRESETS[AppKind.GROK]
    )

    oc_modes = {preset.permission_mode for preset in PERMISSION_PRESETS[AppKind.OPENCODE]}
    assert oc_modes <= {"allow", "ask", "deny"}
    assert all(
        isinstance(preset.always_approve, bool) for preset in PERMISSION_PRESETS[AppKind.OPENCODE]
    )


def test_launcher_selects_claude_permission_preset(tmp_path: Path) -> None:
    provider = _provider(AppKind.CLAUDE, "Claude P")
    # Default preset is bypass (index 0). Move to plan (index 3).
    # app -> provider -> dir -> permissions x3 down -> sessions -> launch
    keys = "\r\r\r\x1b[B\x1b[B\x1b[B\r\r\r"
    plan = _run(tmp_path, [provider], keys)
    assert plan is not None
    assert plan.permission_mode == "plan"
    assert plan.approval_policy is None
    assert plan.sandbox_mode is None


def test_launcher_selects_grok_permission_preset(tmp_path: Path) -> None:
    provider = _provider(AppKind.GROK, "Grok P")
    # Default matches settings workspace+auto (index 1). Move to read-only (index 3).
    # app -> provider -> dir -> permissions x2 down -> sessions -> launch
    keys = "\r\r\r\x1b[B\x1b[B\r\r\r"
    plan = _run(tmp_path, [provider], keys)
    assert plan is not None
    assert plan.sandbox_mode == "read-only"
    assert plan.always_approve is False
    assert plan.permission_mode is None


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

    plan = _run(tmp_path, [provider], _NEW_SESSION_KEYS)

    assert plan is not None
    assert plan.approval_policy is None
    assert plan.sandbox_mode is None
    assert plan.permission_mode is None
    assert plan.always_approve is None


def _write_codex_session(
    settings,
    *,
    session_id: str,
    cwd: Path,
    title: str,
    stamp: str = "2026-08-13T12-00-00",
) -> None:
    import json

    day = settings.codex.user_home / "sessions" / "2026" / "08" / "13"
    day.mkdir(parents=True, exist_ok=True)
    (day / f"rollout-{stamp}-{session_id}.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": session_id,
                            "timestamp": "2026-08-13T04:00:00.000Z",
                            "cwd": str(cwd),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "role": "user",
                            "content": [{"type": "input_text", "text": title}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_launcher_resume_selects_session(tmp_path: Path) -> None:
    provider = _provider(AppKind.CODEX, "Codex P")
    settings = make_app_settings(tmp_path)
    session_cwd = tmp_path / "work"
    session_cwd.mkdir()
    sid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _write_codex_session(settings, session_id=sid, cwd=session_cwd, title="resume me")
    history = LaunchHistory.load(tmp_path / "history.json")
    # Nested under default_cwd still matches this-dir scope.
    # app → provider → dir → permissions → sessions → down (resume) → launch
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


def test_launcher_this_dir_hides_foreign_sessions_until_all_scope(tmp_path: Path) -> None:
    provider = _provider(AppKind.CODEX, "Codex P")
    settings = make_app_settings(tmp_path)
    local = tmp_path / "local"
    foreign = tmp_path.parent / "foreign-project"
    local.mkdir()
    foreign.mkdir()
    local_sid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    foreign_sid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    _write_codex_session(
        settings,
        session_id=local_sid,
        cwd=local,
        title="local session",
        stamp="2026-08-13T12-00-01",
    )
    _write_codex_session(
        settings,
        session_id=foreign_sid,
        cwd=foreign,
        title="foreign session",
        stamp="2026-08-13T12-00-02",
    )
    history = LaunchHistory.load(tmp_path / "history.json")

    # Default this-dir from local: only local session is listed (New + local).
    # app → provider → dir → permissions → sessions → down → launch
    local_plan = _drive(
        lambda: run_launcher(
            settings=settings,
            providers=[provider],
            history=history,
            default_cwd=local,
        ),
        "\r\r\r\r\x1b[B\r\r",
        delay=0.4,
    )
    assert local_plan is not None
    assert local_plan.session is not None
    assert local_plan.session.session_id == local_sid

    # Press 'a' on sessions to show all projects. Newest foreign is listed first
    # after New session, so one down selects it.
    all_plan = _drive(
        lambda: run_launcher(
            settings=settings,
            providers=[provider],
            history=history,
            default_cwd=local,
        ),
        "\r\r\r\ra\x1b[B\r\r",
        delay=0.4,
    )
    assert all_plan is not None
    assert all_plan.session is not None
    assert all_plan.session.session_id == foreign_sid
    assert all_plan.cwd == foreign.resolve()


def test_session_matches_cwd_exact_and_nested(tmp_path: Path) -> None:
    from ccs_plus.tui import _session_matches_cwd

    root = tmp_path / "repo"
    nested = root / "pkg"
    other = tmp_path / "other"
    root.mkdir()
    nested.mkdir()
    other.mkdir()

    assert _session_matches_cwd(str(root), root)
    assert _session_matches_cwd(str(nested), root)
    assert not _session_matches_cwd(str(other), root)
    assert not _session_matches_cwd("", root)
