"""Discover resume-able native CLI sessions under ccs-plus state homes."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from ccs_plus.domain import AppKind
from ccs_plus.home_visibility import CodexHomeVisibility
from ccs_plus.settings import AppSettings

logger = logging.getLogger(__name__)

_MAX_SESSIONS = 80
_TITLE_MAX = 72


@dataclass(frozen=True)
class Session:
    app: AppKind
    session_id: str
    title: str
    cwd: str
    modified_at: float


class SessionReader:
    def prepare(self, settings: AppSettings) -> None:
        pass

    def list(self, home: Path, app: AppKind) -> list[Session]:
        raise NotImplementedError


class CodexSessionReader(SessionReader):
    def prepare(self, settings: AppSettings) -> None:
        CodexHomeVisibility(
            settings.codex.home,
            settings.codex.user_home,
        ).expose_sessions()

    def list(self, home: Path, app: AppKind) -> list[Session]:
        return _list_rollouts(home, app)


class ClaudeSessionReader(SessionReader):
    def list(self, home: Path, app: AppKind) -> list[Session]:
        return _list_project_logs(home, app)


class GrokSessionReader(SessionReader):
    def list(self, home: Path, app: AppKind) -> list[Session]:
        return _list_prompt_histories(home, app)


def session_reader_for(app: AppKind) -> SessionReader:
    readers: dict[AppKind, SessionReader] = {
        AppKind.CODEX: CodexSessionReader(),
        AppKind.CLAUDE: ClaudeSessionReader(),
        AppKind.GROK: GrokSessionReader(),
    }
    return readers[app]


def list_sessions(settings: AppSettings, app: AppKind) -> list[Session]:
    """Return recent sessions for ``app``, newest first."""
    home = settings.state_home(app.value)
    reader = session_reader_for(app)
    try:
        reader.prepare(settings)
        sessions = reader.list(home, app)
    except OSError as exc:
        logger.warning("Unable to list %s sessions under %s: %s", app.value, home, exc)
        return []
    sessions.sort(key=lambda item: item.modified_at, reverse=True)
    return sessions[:_MAX_SESSIONS]


def _list_rollouts(home: Path, app: AppKind) -> list[Session]:
    root = home / "sessions"
    if not root.is_dir():
        return []
    # Stat/sort first so we only parse the newest files (jsonl can be huge).
    ranked = _newest_files(root.rglob("rollout-*.jsonl"), limit=_MAX_SESSIONS * 2)
    sessions: list[Session] = []
    for path in ranked:
        session = _parse_rollout(path, app)
        if session is not None:
            sessions.append(session)
        if len(sessions) >= _MAX_SESSIONS:
            break
    return sessions


def _parse_rollout(path: Path, app: AppKind) -> Session | None:
    session_id = ""
    cwd = ""
    title = ""
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        return None
    # Filename embeds UUID: rollout-...-<uuid>.jsonl
    parts = path.stem.split("-")
    if len(parts) >= 5:
        candidate_id = "-".join(parts[-5:])
        if len(candidate_id) >= 36:
            session_id = candidate_id
    try:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index > 40:
                    break
                # Huge first-line payloads (skills blobs) — skip if oversized.
                if len(line) > 64_000 and index > 0:
                    continue
                try:
                    document = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = document.get("type")
                if kind == "session_meta":
                    payload = document.get("payload")
                    if isinstance(payload, dict):
                        session_id = str(
                            payload.get("id") or payload.get("session_id") or session_id
                        )
                        cwd = str(payload.get("cwd") or "")
                elif kind == "response_item" and not title:
                    payload = document.get("payload")
                    if isinstance(payload, dict) and payload.get("role") == "user":
                        candidate = _text_from_content(payload.get("content"))
                        if candidate and not candidate.startswith("<"):
                            title = candidate
                if session_id and cwd and title:
                    break
                if session_id and cwd and index >= 8:
                    # Title is optional polish; stop early once identity is known.
                    break
    except OSError:
        return None
    if not session_id:
        return None
    if not title:
        title = Path(cwd).name if cwd else session_id[:8]
    return Session(
        app=app,
        session_id=session_id,
        title=_clip(title),
        cwd=cwd,
        modified_at=timestamp,
    )


def _newest_files(paths: Iterable[Path], *, limit: int) -> list[Path]:
    ranked: list[tuple[float, Path]] = []
    for path in paths:
        try:
            if path.is_file():
                ranked.append((path.stat().st_mtime, path))
        except OSError:
            continue
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in ranked[:limit]]


def _list_project_logs(home: Path, app: AppKind) -> list[Session]:
    root = home / "projects"
    if not root.is_dir():
        return []
    paths: list[Path] = []
    try:
        for project in root.iterdir():
            if project.is_dir():
                paths.extend(project.glob("*.jsonl"))
    except OSError:
        return []
    ranked = _newest_files(paths, limit=_MAX_SESSIONS * 2)
    sessions: list[Session] = []
    for path in ranked:
        session = _parse_project_log(path, app)
        if session is not None:
            sessions.append(session)
        if len(sessions) >= _MAX_SESSIONS:
            break
    return sessions


def _parse_project_log(path: Path, app: AppKind) -> Session | None:
    session_id = path.stem
    cwd = ""
    title = ""
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index > 40:
                    break
                if len(line) > 64_000:
                    continue
                try:
                    document = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(document, dict):
                    continue
                sid = document.get("sessionId")
                if isinstance(sid, str) and sid:
                    session_id = sid
                if not cwd and isinstance(document.get("cwd"), str):
                    cwd = document["cwd"]
                if document.get("type") == "user" and not title:
                    message = document.get("message")
                    if isinstance(message, dict):
                        candidate = _text_from_content(message.get("content"))
                    else:
                        candidate = _text_from_content(message)
                    if candidate:
                        title = candidate
                if document.get("type") == "summary" and not title:
                    summary = document.get("summary")
                    if isinstance(summary, str) and summary.strip():
                        title = summary.strip()
                if session_id and title and cwd:
                    break
                if session_id and cwd and index >= 8:
                    break
    except OSError:
        return None
    if not session_id:
        return None
    if not title:
        title = Path(cwd).name if cwd else session_id[:8]
    return Session(
        app=app,
        session_id=session_id,
        title=_clip(title),
        cwd=cwd,
        modified_at=timestamp,
    )


def _list_prompt_histories(home: Path, app: AppKind) -> list[Session]:
    root = home / "sessions"
    if not root.is_dir():
        return []
    by_id: dict[str, Session] = {}
    for history_path in root.glob("*/prompt_history.jsonl"):
        if not history_path.is_file():
            continue
        encoded = history_path.parent.name
        cwd = unquote(encoded)
        try:
            with history_path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        document = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(document, dict):
                        continue
                    session_id = document.get("session_id")
                    if not isinstance(session_id, str) or not session_id:
                        continue
                    prompt = document.get("prompt")
                    title = prompt.strip() if isinstance(prompt, str) else ""
                    raw_ts = document.get("timestamp")
                    if isinstance(raw_ts, str):
                        timestamp = _parse_iso(raw_ts) or history_path.stat().st_mtime
                    else:
                        timestamp = history_path.stat().st_mtime
                    if timestamp is None:
                        timestamp = history_path.stat().st_mtime
                    existing = by_id.get(session_id)
                    if existing is None:
                        by_id[session_id] = Session(
                            app=app,
                            session_id=session_id,
                            title=_clip(title or Path(cwd).name or session_id[:8]),
                            cwd=cwd,
                            modified_at=timestamp,
                        )
                    elif timestamp > existing.modified_at:
                        by_id[session_id] = Session(
                            app=existing.app,
                            session_id=existing.session_id,
                            title=existing.title,
                            cwd=existing.cwd or cwd,
                            modified_at=timestamp,
                        )
        except OSError:
            continue
    return list(by_id.values())


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()
    return ""


def _parse_iso(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _clip(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= _TITLE_MAX:
        return cleaned
    return cleaned[: _TITLE_MAX - 1] + "…"
