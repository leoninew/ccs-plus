from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from conftest import make_app_settings

from ccs_plus.domain import AppKind
from ccs_plus.sessions import list_sessions


def test_list_codex_sessions_parses_rollout_meta(tmp_path: Path) -> None:
    settings = make_app_settings(tmp_path)
    day = settings.codex.user_home / "sessions" / "2026" / "08" / "13"
    day.mkdir(parents=True)
    path = day / "rollout-2026-08-13T10-00-00-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                            "timestamp": "2026-08-13T02:00:00.000Z",
                            "cwd": str(tmp_path / "project"),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "role": "user",
                            "content": [{"type": "input_text", "text": "fix the flaky test"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "project").mkdir()

    sessions = list_sessions(settings, AppKind.CODEX)

    assert len(sessions) == 1
    assert sessions[0].session_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert sessions[0].title == "fix the flaky test"
    assert sessions[0].cwd == str(tmp_path / "project")


def test_list_claude_sessions_parses_project_jsonl(tmp_path: Path) -> None:
    settings = make_app_settings(tmp_path)
    project = settings.claude.home / "projects" / "-tmp-demo"
    project.mkdir(parents=True)
    path = project / "11111111-2222-3333-4444-555555555555.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": "11111111-2222-3333-4444-555555555555",
                "cwd": str(tmp_path / "demo"),
                "timestamp": "2026-08-13T03:00:00.000Z",
                "message": {"role": "user", "content": "summarize the PR"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "demo").mkdir()

    sessions = list_sessions(settings, AppKind.CLAUDE)

    assert len(sessions) == 1
    assert sessions[0].session_id == "11111111-2222-3333-4444-555555555555"
    assert sessions[0].title == "summarize the PR"


def test_list_grok_sessions_groups_prompt_history(tmp_path: Path) -> None:
    settings = make_app_settings(tmp_path)
    cwd = str(tmp_path / "repo")
    folder = settings.grok.home / "sessions" / quote(cwd, safe="")
    folder.mkdir(parents=True)
    path = folder / "prompt_history.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "session_id": "g1",
                        "prompt": "first prompt",
                        "timestamp": "2026-08-13T01:00:00.000Z",
                    }
                ),
                json.dumps(
                    {
                        "session_id": "g1",
                        "prompt": "second prompt",
                        "timestamp": "2026-08-13T04:00:00.000Z",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    sessions = list_sessions(settings, AppKind.GROK)

    assert len(sessions) == 1
    assert sessions[0].session_id == "g1"
    assert sessions[0].title == "first prompt"
    assert sessions[0].cwd == cwd


def test_list_opencode_sessions_reads_sqlite(tmp_path: Path) -> None:
    settings = make_app_settings(tmp_path)
    db_dir = settings.opencode.home / "share" / "opencode"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "opencode.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            directory TEXT NOT NULL,
            title TEXT NOT NULL,
            version TEXT NOT NULL,
            cost REAL DEFAULT 0 NOT NULL,
            tokens_input INTEGER DEFAULT 0 NOT NULL,
            tokens_output INTEGER DEFAULT 0 NOT NULL,
            tokens_reasoning INTEGER DEFAULT 0 NOT NULL,
            tokens_cache_read INTEGER DEFAULT 0 NOT NULL,
            tokens_cache_write INTEGER DEFAULT 0 NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            time_archived INTEGER
        )
        """
    )
    cwd = str(tmp_path / "project")
    conn.execute(
        """
        INSERT INTO session (
            id, project_id, slug, directory, title, version,
            time_created, time_updated, time_archived
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ses_abc",
            "proj1",
            "slug",
            cwd,
            "OpenCode session title",
            "1.0",
            1_700_000_000_000,
            1_700_000_100_000,
            None,
        ),
    )
    conn.commit()
    conn.close()

    sessions = list_sessions(settings, AppKind.OPENCODE)

    assert len(sessions) == 1
    assert sessions[0].session_id == "ses_abc"
    assert sessions[0].title == "OpenCode session title"
    assert sessions[0].cwd == cwd
