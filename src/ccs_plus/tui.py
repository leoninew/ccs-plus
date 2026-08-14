"""Opencode-style multi-pane interactive launcher (prompt_toolkit)."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText, StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import (
    ConditionalContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
    WindowAlign,
)
from prompt_toolkit.layout.containers import FloatContainer
from prompt_toolkit.layout.dimension import Dimension as D
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.validation import ValidationError, Validator
from prompt_toolkit.widgets import Box, TextArea

from ccs_plus.adapters import display_configuration, runtime_from_provider
from ccs_plus.domain import AppKind, Provider, ProviderError
from ccs_plus.launch_history import LaunchHistory
from ccs_plus.sessions import Session, list_sessions
from ccs_plus.settings import AppSettings

# High-contrast neon-on-dark (bright selection, clear active pane).
STYLE = Style.from_dict(
    {
        "root": "bg:#0a0e14 #d0d7e2",
        "header": "bg:#010409 #8b949e",
        "header.brand": "bg:#010409 #58a6ff bold",
        "header.accent": "bg:#010409 #d2a8ff bold",
        "header.mode": "bg:#010409 #3fb950 bold",
        "footer": "bg:#010409 #6e7681",
        "footer.key": "bg:#010409 #f0f6fc bold",
        "footer.filter": "bg:#010409 #ffa657 bold",
        "frame.border": "#30363d",
        "frame.label": "#8b949e",
        "frame.active.border": "#58a6ff bold",
        "frame.active.label": "#58a6ff bold",
        "frame.scroll": "#8b949e",
        "frame.active.scroll": "#58a6ff bold",
        "item": "#c9d1d9",
        "item.selected": "bg:#21262d #f0f6fc bold",
        "item.focused": "bg:#1f6feb #ffffff bold",
        "item.focused-sub": "bg:#1f6feb #dbeafe",
        "item.muted": "#8b949e",
        "badge.claude": "bg:#d97706 #0a0e14 bold",
        "badge.codex": "bg:#10b981 #0a0e14 bold",
        "badge.grok": "bg:#a855f7 #0a0e14 bold",
        "badge.claude.focused": "bg:#fbbf24 #0a0e14 bold",
        "badge.codex.focused": "bg:#34d399 #0a0e14 bold",
        "badge.grok.focused": "bg:#c084fc #0a0e14 bold",
        "status.ok": "#3fb950 bold",
        "status.err": "#ff7b72 bold",
        "button.launch": "bg:#238636 #ffffff bold",
        "button.launch.focused": "bg:#3fb950 #000000 bold underline",
        "button.cancel": "bg:#6e2121 #ffffff bold",
        "button.cancel.focused": "bg:#ff7b72 #000000 bold underline",
        "text-area": "bg:#0d1117 #f0f6fc",
        "text-area.focused": "bg:#161b22 #ffffff bold",
    }
)

_SESSION_ROW = 2
_PROVIDER_ROW = 2
_PERMISSION_ROW = 2

SessionScope = Literal["this_dir", "all"]


@dataclass(frozen=True)
class ApprovalPreset:
    key: str
    label: str
    approval_policy: str
    sandbox_mode: str
    description: str


APPROVAL_PRESETS: tuple[ApprovalPreset, ...] = (
    ApprovalPreset(
        "yolo",
        "YOLO",
        "never",
        "danger-full-access",
        "never ask · full disk access",
    ),
    ApprovalPreset(
        "on-request",
        "On request",
        "on-request",
        "workspace-write",
        "ask when needed · workspace write",
    ),
    ApprovalPreset(
        "auto-workspace",
        "Auto (workspace)",
        "never",
        "workspace-write",
        "never ask · workspace write",
    ),
    ApprovalPreset(
        "ask",
        "Ask",
        "on-failure",
        "workspace-write",
        "ask on failure · workspace write",
    ),
)


@dataclass(frozen=True)
class LaunchPlan:
    provider: Provider
    cwd: Path
    session: Session | None
    approval_policy: str | None
    sandbox_mode: str | None


def run_launcher(
    *,
    settings: AppSettings,
    providers: Sequence[Provider],
    history: LaunchHistory,
    default_cwd: Path | None = None,
) -> LaunchPlan | None:
    """Show the multi-pane launcher and return a launch plan, or None on cancel."""
    screen = _LaunchScreen(
        settings=settings,
        providers=list(providers),
        history=history,
        default_cwd=(default_cwd or Path.cwd()).resolve(),
    )
    return screen.run()


class _ExistingDirectoryValidator(Validator):
    def validate(self, document: Document) -> None:
        text = document.text.strip()
        if not text:
            return
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_dir():
            raise ValidationError(
                message=f"Directory does not exist: {path}",
                cursor_position=len(document.text),
            )


class _ScrollListControl(FormattedTextControl):
    """List control: app-level keys; mouse click + wheel handled here."""

    def __init__(
        self,
        get_text: Callable[[], Any],
        *,
        on_click_row: Callable[[int], None],
        on_scroll: Callable[[int], None],
        on_activate: Callable[[], None],
    ) -> None:
        # focusable=True so the window reliably receives mouse wheel events.
        # Arrow keys are still handled by eager app-level bindings.
        super().__init__(get_text, focusable=True, show_cursor=False, modal=False)
        self._on_click_row = on_click_row
        self._on_scroll = on_scroll
        self._on_activate = on_activate

    def mouse_handler(self, mouse_event: MouseEvent) -> object:
        # Prefer MOUSE_DOWN for selection: changing focus on down would otherwise
        # drop the matching MOUSE_UP on another control.
        event = mouse_event.event_type
        if event == MouseEventType.SCROLL_UP:
            self._on_activate()
            self._on_scroll(-1)
            with contextlib.suppress(Exception):
                get_app().invalidate()
            return None
        if event == MouseEventType.SCROLL_DOWN:
            self._on_activate()
            self._on_scroll(1)
            with contextlib.suppress(Exception):
                get_app().invalidate()
            return None
        if event == MouseEventType.MOUSE_DOWN:
            # Fragment-level handlers (3-tuples) are dispatched by the base class.
            result = super().mouse_handler(mouse_event)
            if result is not NotImplemented:
                return result
            # Fallback: map y → row for plain 2-tuple lines.
            self._on_activate()
            self._on_click_row(mouse_event.position.y)
            with contextlib.suppress(Exception):
                get_app().invalidate()
            return None
        # Consume UP so Window default handlers don't steal it.
        if event == MouseEventType.MOUSE_UP:
            return None
        return NotImplemented


def _fuzzy_match(query: str, *parts: str) -> bool:
    """Case-insensitive subsequence match across joined parts."""
    needle = "".join(query.split()).casefold()
    if not needle:
        return True
    hay = " ".join(parts).casefold()
    if needle in hay.replace(" ", ""):
        return True
    if needle in hay:
        return True
    pos = 0
    for char in needle:
        pos = hay.find(char, pos)
        if pos < 0:
            return False
        pos += 1
    return True


def _normalize_cwd(path: str | Path) -> Path | None:
    try:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def _session_matches_cwd(session_cwd: str, scope_cwd: Path) -> bool:
    """True when the session belongs to scope_cwd (exact or nested under it)."""
    if not session_cwd:
        return False
    session_path = _normalize_cwd(session_cwd)
    if session_path is None:
        return False
    try:
        scope = scope_cwd.resolve()
    except (OSError, RuntimeError):
        scope = scope_cwd
    if os.path.normcase(str(session_path)) == os.path.normcase(str(scope)):
        return True
    try:
        session_path.relative_to(scope)
        return True
    except ValueError:
        return False


class _LaunchScreen:
    """Single-screen launcher: config (left) | sessions (right)."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        providers: list[Provider],
        history: LaunchHistory,
        default_cwd: Path,
    ) -> None:
        self.settings = settings
        self.history = history
        self.default_cwd = default_cwd
        self._all_providers = providers
        self.apps = [app for app in AppKind if any(p.app is app for p in providers)]
        if not self.apps:
            self.apps = list(AppKind)

        self.app_index = 0
        last_app = self._last_used_app()
        if last_app is not None and last_app in self.apps:
            self.app_index = self.apps.index(last_app)

        self.session_index = 0
        self.provider_index = 0
        self.button_index = 0
        self.focus = "app"
        self.status = ""
        self.status_error = False
        self._sessions_cache: dict[AppKind, list[Session]] = {}
        self._filtered_sessions_cache: list[Session] | None = None
        self._filtered_providers_cache: list[Provider] | None = None
        self._provider_scroll = 0
        self._session_scroll = 0
        self.provider_filter = ""
        self.session_filter = ""
        self.filter_mode = False
        # Default: only sessions for the launch/working directory (like native CLIs).
        self.sessions_scope: SessionScope = "this_dir"

        self.dir_area = TextArea(
            text=str(default_cwd),
            multiline=False,
            completer=PathCompleter(only_directories=True, expanduser=True),
            validator=_ExistingDirectoryValidator(),
            style="class:text-area",
            height=1,
            focusable=Condition(
                lambda: (
                    self.selected_session is None and self.focus == "dir" and not self.filter_mode
                )
            ),
        )
        self.dir_buffer = self.dir_area.buffer

        self._focus_sink = Window(
            content=FormattedTextControl("", focusable=True, show_cursor=False),
            height=0,
            dont_extend_height=True,
        )

        self._sync_provider_index()
        self._sync_permission_selection()
        self._build_application()

    def run(self) -> LaunchPlan | None:
        result: LaunchPlan | None = self.application.run()
        return result

    # --- data helpers -------------------------------------------------

    def _last_used_app(self) -> AppKind | None:
        best: AppKind | None = None
        best_ts = -1
        for app in AppKind:
            for provider in self._all_providers:
                if provider.app is not app:
                    continue
                usage = self.history.usage(provider)
                if usage.last_launched_at > best_ts:
                    best_ts = usage.last_launched_at
                    best = app
        return best

    def _default_permission_index(self) -> int:
        policy, sandbox = self._effective_permissions()
        for index, preset in enumerate(APPROVAL_PRESETS):
            if preset.approval_policy == policy and preset.sandbox_mode == sandbox:
                return index
        return 0

    def _effective_permissions(self) -> tuple[str, str]:
        policy = self.settings.codex.approval_policy
        sandbox = self.settings.codex.sandbox_mode
        provider = self.current_provider
        if provider is not None and provider.app.supports_permission_overrides:
            try:
                runtime = runtime_from_provider(provider)
            except ProviderError:
                pass
            else:
                provider_policy, provider_sandbox = runtime.permission_overrides()
                policy = provider_policy or policy
                sandbox = provider_sandbox or sandbox
        return policy, sandbox

    def _sync_permission_selection(self) -> None:
        if self.current_app.supports_permission_overrides:
            self.permission_index = self._default_permission_index()
        else:
            self.permission_index = 0
        self.permission_override = False

    @property
    def current_app(self) -> AppKind:
        return self.apps[self.app_index]

    @property
    def all_app_providers(self) -> list[Provider]:
        return [provider for provider in self._all_providers if provider.app is self.current_app]

    @property
    def filtered_providers(self) -> list[Provider]:
        if self._filtered_providers_cache is not None:
            return self._filtered_providers_cache
        providers = self.all_app_providers
        query = self.provider_filter
        if not query:
            self._filtered_providers_cache = providers
            return providers
        result: list[Provider] = []
        for provider in providers:
            display = display_configuration(provider)
            if _fuzzy_match(query, provider.name, display.model or "", provider.id):
                result.append(provider)
        self._filtered_providers_cache = result
        return result

    @property
    def current_provider(self) -> Provider | None:
        providers = self.filtered_providers
        if not providers:
            return None
        return providers[min(self.provider_index, len(providers) - 1)]

    @property
    def all_sessions(self) -> list[Session]:
        app = self.current_app
        if app not in self._sessions_cache:
            self._sessions_cache[app] = list_sessions(self.settings, app)
        return self._sessions_cache[app]

    @property
    def filtered_sessions(self) -> list[Session]:
        if self._filtered_sessions_cache is not None:
            return self._filtered_sessions_cache
        sessions = self.all_sessions
        if self.sessions_scope == "this_dir":
            scope_cwd = self._session_scope_cwd()
            sessions = [
                session for session in sessions if _session_matches_cwd(session.cwd, scope_cwd)
            ]
        query = self.session_filter
        if query:
            sessions = [
                session
                for session in sessions
                if _fuzzy_match(query, session.title, session.cwd, session.session_id)
            ]
        self._filtered_sessions_cache = sessions
        return sessions

    def _session_scope_cwd(self) -> Path:
        """Directory used for the 'this dir' session scope.

        Prefer a valid path from the directory field while creating a new
        session; otherwise fall back to the launcher's default cwd.
        """
        if self.selected_session is None:
            text = self.dir_buffer.text.strip()
            if text:
                path = Path(text).expanduser()
                path = (Path.cwd() / path).resolve() if not path.is_absolute() else path.resolve()
                if path.is_dir():
                    return path
        return self.default_cwd

    def _invalidate_provider_filter(self) -> None:
        self._filtered_providers_cache = None

    def _invalidate_session_filter(self) -> None:
        self._filtered_sessions_cache = None

    def _toggle_sessions_scope(self) -> None:
        self.sessions_scope = "all" if self.sessions_scope == "this_dir" else "this_dir"
        self._invalidate_session_filter()
        self.session_index = 0
        self._session_scroll = 0
        self._clamp_session_index()

    @property
    def selected_session(self) -> Session | None:
        if self.session_index <= 0:
            return None
        sessions = self.filtered_sessions
        index = self.session_index - 1
        if 0 <= index < len(sessions):
            return sessions[index]
        return None

    @property
    def current_preset(self) -> ApprovalPreset:
        return APPROVAL_PRESETS[self.permission_index]

    def _session_entry_count(self) -> int:
        return 1 + len(self.filtered_sessions)

    def _sync_provider_index(self) -> None:
        providers = self.filtered_providers
        default_id = self.history.default_provider_id(self.current_app, self.all_app_providers)
        if default_id:
            for index, provider in enumerate(providers):
                if provider.id == default_id:
                    self.provider_index = index
                    self._provider_scroll = 0
                    return
        self.provider_index = 0
        self._provider_scroll = 0

    def _set_app(self, index: int) -> None:
        if index == self.app_index:
            return
        self.app_index = index
        self.session_index = 0
        self._session_scroll = 0
        self.provider_filter = ""
        self.session_filter = ""
        self.filter_mode = False
        self._invalidate_provider_filter()
        self._invalidate_session_filter()
        self._sync_provider_index()
        self._sync_permission_selection()
        self._write_directory(str(self.default_cwd))
        self.status = ""
        self.status_error = False
        if self.focus == "permissions" and not self.current_app.supports_permission_overrides:
            self.focus = "dir" if self.selected_session is None else "provider"
        if self.focus == "dir" and self.selected_session is not None:
            self.focus = "sessions"
        self._ensure_provider_visible()
        self._ensure_session_visible()
        self._sync_layout_focus()

    def _set_session(self, index: int) -> None:
        max_index = max(0, self._session_entry_count() - 1)
        self.session_index = max(0, min(index, max_index))
        if self.selected_session is not None and self.focus == "dir":
            self.focus = "sessions"
            self._sync_layout_focus()
        self._ensure_session_visible()

    def _write_directory(self, text: str) -> None:
        if self.dir_buffer.text == text:
            return
        self.dir_buffer.set_document(Document(text, len(text)), bypass_readonly=True)
        if self.sessions_scope == "this_dir":
            self._invalidate_session_filter()
            self._clamp_session_index()

    def _focus_order(self) -> list[str]:
        order = ["app", "provider"]
        if self.selected_session is None:
            order.append("dir")
        if self.current_app.supports_permission_overrides:
            order.append("permissions")
        order.extend(["sessions", "buttons"])
        return order

    def _set_focus(self, pane: str) -> None:
        order = self._focus_order()
        if pane not in order:
            pane = order[0]
        previous = self.focus
        if pane not in {"provider", "sessions"}:
            self.filter_mode = False
        self.focus = pane
        if previous == "dir" and pane != "dir" and self.sessions_scope == "this_dir":
            self._invalidate_session_filter()
            self._clamp_session_index()
        self._sync_layout_focus()

    def _move_focus(self, delta: int) -> None:
        self.filter_mode = False
        order = self._focus_order()
        previous = self.focus
        if self.focus not in order:
            self.focus = order[0]
        else:
            index = order.index(self.focus)
            self.focus = order[(index + delta) % len(order)]
        if previous == "dir" and self.focus != "dir" and self.sessions_scope == "this_dir":
            self._invalidate_session_filter()
            self._clamp_session_index()
        self._sync_layout_focus()

    def _sync_layout_focus(self) -> None:
        if self.focus == "dir" and self.selected_session is None and not self.filter_mode:
            with contextlib.suppress(Exception):
                self.application.layout.focus(self.dir_area)
            return
        target = {
            "app": getattr(self, "_app_window", None),
            "provider": getattr(self, "_provider_window", None),
            "permissions": getattr(self, "_permission_window", None),
            "sessions": getattr(self, "_sessions_window", None),
            "buttons": getattr(self, "_buttons_window", None),
        }.get(self.focus)
        if target is not None:
            with contextlib.suppress(Exception):
                self.application.layout.focus(target)
                return
        with contextlib.suppress(Exception):
            self.application.layout.focus(self._focus_sink)

    def _provider_capacity(self) -> int:
        return max(
            1,
            self._visible_lines(getattr(self, "_provider_window", None), default=8)
            // _PROVIDER_ROW,
        )

    def _session_capacity(self) -> int:
        return max(
            1,
            self._visible_lines(getattr(self, "_sessions_window", None), default=16)
            // _SESSION_ROW,
        )

    def _ensure_provider_visible(self) -> None:
        count = len(self.filtered_providers)
        capacity = self._provider_capacity()
        max_scroll = max(0, count - capacity)
        if self.provider_index < self._provider_scroll:
            self._provider_scroll = self.provider_index
        elif self.provider_index >= self._provider_scroll + capacity:
            self._provider_scroll = self.provider_index - capacity + 1
        self._provider_scroll = max(0, min(self._provider_scroll, max_scroll))

    def _ensure_session_visible(self) -> None:
        count = self._session_entry_count()
        capacity = self._session_capacity()
        max_scroll = max(0, count - capacity)
        if self.session_index < self._session_scroll:
            self._session_scroll = self.session_index
        elif self.session_index >= self._session_scroll + capacity:
            self._session_scroll = self.session_index - capacity + 1
        self._session_scroll = max(0, min(self._session_scroll, max_scroll))

    def _visible_lines(self, window: Window | None, *, default: int) -> int:
        if window is None:
            return default
        info = window.render_info
        if info is None:
            return default
        return max(1, info.window_height)

    def _clamp_provider_index(self) -> None:
        providers = self.filtered_providers
        if not providers:
            self.provider_index = 0
        else:
            self.provider_index = max(0, min(self.provider_index, len(providers) - 1))
        self._sync_permission_selection()
        self._ensure_provider_visible()

    def _clamp_session_index(self) -> None:
        max_index = max(0, self._session_entry_count() - 1)
        self.session_index = max(0, min(self.session_index, max_index))
        self._ensure_session_visible()

    # --- filter -------------------------------------------------------

    def _active_filter(self) -> str:
        if self.focus == "provider":
            return self.provider_filter
        if self.focus == "sessions":
            return self.session_filter
        return ""

    def _set_active_filter(self, value: str) -> None:
        if self.focus == "provider":
            self.provider_filter = value
            self._invalidate_provider_filter()
            self._clamp_provider_index()
        elif self.focus == "sessions":
            self.session_filter = value
            self._invalidate_session_filter()
            self._clamp_session_index()

    def _start_filter(self) -> None:
        if self.focus not in {"provider", "sessions"}:
            return
        self.filter_mode = True
        self._sync_layout_focus()

    def _filter_append(self, text: str) -> None:
        if not self.filter_mode:
            return
        self._set_active_filter(self._active_filter() + text)

    def _filter_backspace(self) -> None:
        if not self.filter_mode:
            return
        current = self._active_filter()
        if current:
            self._set_active_filter(current[:-1])
        else:
            self.filter_mode = False

    def _clear_filter(self) -> None:
        if self.focus == "provider":
            self.provider_filter = ""
            self._invalidate_provider_filter()
            self._clamp_provider_index()
        elif self.focus == "sessions":
            self.session_filter = ""
            self._invalidate_session_filter()
            self._clamp_session_index()
        self.filter_mode = False

    # --- launch / cancel ----------------------------------------------

    def _cancel(self) -> None:
        self.application.exit(result=None)

    def _try_launch(self) -> None:
        provider = self.current_provider
        if provider is None:
            self.status = f"No matching {self.current_app.display_name} providers."
            self.status_error = True
            return
        session = self.selected_session
        if session is not None:
            cwd_text = session.cwd or str(self.default_cwd)
        else:
            cwd_text = self.dir_buffer.text.strip() or str(self.default_cwd)
        path = Path(cwd_text).expanduser()
        path = (Path.cwd() / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_dir():
            self.status = f"Directory does not exist: {path}"
            self.status_error = True
            if session is None:
                self._set_focus("dir")
            return
        approval: str | None = None
        sandbox: str | None = None
        if self.current_app.supports_permission_overrides:
            preset = self.current_preset
            if self.permission_override:
                approval = preset.approval_policy
                sandbox = preset.sandbox_mode
        self.application.exit(
            result=LaunchPlan(
                provider=provider,
                cwd=path,
                session=session,
                approval_policy=approval,
                sandbox_mode=sandbox,
            )
        )

    # --- rendering ----------------------------------------------------

    def _header_text(self) -> StyleAndTextTuples:
        provider = self.current_provider
        name = provider.name if provider else "—"
        mode = "resume" if self.selected_session else "new"
        app = self.current_app
        badge_style = f"class:badge.{app.style_key}"
        return [
            ("class:header.brand", " ccs-plus "),
            ("class:header", "▸ "),
            (badge_style, f" {app.badge} "),
            ("class:header.accent", f" {app.display_name}"),
            ("class:header", f" · {name} · "),
            ("class:header.mode", mode),
            ("class:header", " "),
        ]

    def _footer_text(self) -> StyleAndTextTuples:
        pane = self.focus
        parts: StyleAndTextTuples = [
            ("class:footer", " "),
            ("class:footer.key", pane),
            ("class:footer", " · "),
            ("class:footer.key", "tab"),
            ("class:footer", " · "),
            ("class:footer.key", "↑↓"),
            ("class:footer", " · "),
            ("class:footer.key", "enter"),
            ("class:footer", " · "),
            ("class:footer.key", "/"),
            ("class:footer", " filter · "),
            ("class:footer.key", "a"),
            ("class:footer", " scope · "),
            ("class:footer.key", "esc"),
            ("class:footer", " "),
        ]
        filt = self._active_filter()
        if self.filter_mode or filt:
            parts.extend(
                [
                    ("class:footer", "│ "),
                    ("class:footer.filter", f"/{filt}█ " if self.filter_mode else f"/{filt} "),
                ]
            )
        if self.status:
            style = "class:status.err" if self.status_error else "class:status.ok"
            parts.extend([("class:footer", "│ "), (style, f"{self.status} ")])
        return parts

    def _pane_border_style(self, pane: str) -> str:
        return "class:frame.active.border" if self.focus == pane else "class:frame.border"

    def _pane_label_style(self, pane: str) -> str:
        return "class:frame.active.label" if self.focus == pane else "class:frame.label"

    def _pane_title_text(self, pane: str, label: str) -> str:
        filt = ""
        if pane == "provider" and self.provider_filter:
            filt = f" /{self.provider_filter}"
        elif pane == "sessions":
            scope = "this dir" if self.sessions_scope == "this_dir" else "all"
            filt = f" · {scope}"
            if self.session_filter:
                filt += f" /{self.session_filter}"
        if self.focus == pane:
            suffix = " · filter" if self.filter_mode and pane in {"provider", "sessions"} else ""
            return f" ▶ {label}{filt}{suffix} "
        return f" {label}{filt} "

    def _window_width(self, pane: str, default: int = 40) -> int:
        win = {
            "app": getattr(self, "_app_window", None),
            "provider": getattr(self, "_provider_window", None),
            "permissions": getattr(self, "_permission_window", None),
            "sessions": getattr(self, "_sessions_window", None),
        }.get(pane)
        info = getattr(win, "render_info", None) if win is not None else None
        width = getattr(info, "window_width", None) if info is not None else None
        if isinstance(width, int):
            return max(12, width + 2)
        return default

    def _highlighted_frame(self, body: Any, pane: str, label: str) -> Any:
        """Stable frame tree: body stays put so mouse hit-testing keeps working.

        Only border glyphs/styles are recomputed each paint via FormattedTextControl
        callables. DynamicContainer must NOT wrap the body — rebuilding the tree
        every frame drops mouse handlers.
        """

        def top_text() -> StyleAndTextTuples:
            border = self._pane_border_style(pane)
            label_style = self._pane_label_style(pane)
            title = self._pane_title_text(pane, label)
            if self.focus == pane:
                tl, tr, h = "╔", "╗", "═"
            else:
                tl, tr, h = "┌", "┐", "─"
            width = self._window_width(pane)
            inner = max(0, width - 2)
            title_text = title if len(title) <= inner else title[: max(0, inner - 1)] + "…"
            pad = max(0, inner - len(title_text))
            left_pad = 1 if pad else 0
            right_pad = max(0, pad - left_pad)
            return [
                (border, tl + h * left_pad),
                (label_style, title_text),
                (border, h * right_pad + tr),
            ]

        def bottom_text() -> StyleAndTextTuples:
            border = self._pane_border_style(pane)
            bl, br, h = ("╚", "╝", "═") if self.focus == pane else ("└", "┘", "─")
            width = self._window_width(pane)
            return [(border, bl + h * max(0, width - 2) + br)]

        def vert_text() -> StyleAndTextTuples:
            border = self._pane_border_style(pane)
            glyph = "║" if self.focus == pane else "│"
            # Enough lines to fill tall panes; Window clips to its height.
            height = 80
            win = {
                "app": getattr(self, "_app_window", None),
                "provider": getattr(self, "_provider_window", None),
                "permissions": getattr(self, "_permission_window", None),
                "sessions": getattr(self, "_sessions_window", None),
            }.get(pane)
            info = getattr(win, "render_info", None) if win is not None else None
            if info is not None:
                height = max(1, info.window_height)
            return [(border, (glyph + "\n") * height)]

        top = Window(
            FormattedTextControl(top_text, focusable=False, show_cursor=False),
            height=1,
            dont_extend_height=True,
        )
        bottom = Window(
            FormattedTextControl(bottom_text, focusable=False, show_cursor=False),
            height=1,
            dont_extend_height=True,
        )
        left = Window(
            FormattedTextControl(vert_text, focusable=False, show_cursor=False),
            width=1,
            dont_extend_width=True,
        )
        right = Window(
            FormattedTextControl(vert_text, focusable=False, show_cursor=False),
            width=1,
            dont_extend_width=True,
        )
        return HSplit([top, VSplit([left, body, right]), bottom], style="class:frame")

    def _append_entry(
        self,
        lines: StyleAndTextTuples,
        *,
        focused: bool,
        selected: bool,
        title: str,
        subtitle: str,
        mouse_handler: Callable[[MouseEvent], object] | None = None,
    ) -> None:
        style = self._row_style(focused=focused and selected, selected=selected)
        sub_style = "class:item.focused-sub" if focused and selected else "class:item.muted"
        marker = "▸ " if selected else "  "
        title_text = f"{marker}{title}\n"
        sub_text = f"    {subtitle}\n"
        if mouse_handler is None:
            lines.append((style, title_text))
            lines.append((sub_style, sub_text))
        else:
            # 3-tuple fragments register per-cell mouse handlers in FormattedTextControl.
            lines.append((style, title_text, mouse_handler))
            lines.append((sub_style, sub_text, mouse_handler))

    def _session_lines(self) -> StyleAndTextTuples:
        lines: StyleAndTextTuples = []
        scope_hint = (
            f"in {_short_path(str(self._session_scope_cwd()))}"
            if self.sessions_scope == "this_dir"
            else "any project"
        )
        entries: list[tuple[int, str, str]] = [(-1, "New session", f"start fresh · {scope_hint}")]
        for index, session in enumerate(self.filtered_sessions):
            when = _relative_time(session.modified_at)
            subtitle = f"{_short_path(session.cwd)} · {when}" if session.cwd else when
            entries.append((index, session.title or session.session_id[:8], subtitle))
        if len(entries) == 1 and self.session_filter:
            entries.append((-2, "(no matches)", f"filter: {self.session_filter}"))
        elif len(entries) == 1 and self.sessions_scope == "this_dir":
            entries.append((-2, "(no sessions here)", "press a for all projects"))
        elif len(entries) == 1:
            entries.append((-2, "(no sessions)", "launch first to populate"))

        # Windowed render only — prevents highlight overflow past the pane.
        capacity = self._session_capacity()
        start = max(0, min(self._session_scroll, max(0, len(entries) - 1)))
        end = min(len(entries), start + capacity)
        focused = self.focus == "sessions"
        for row in range(start, end):
            key, title, subtitle = entries[row]
            selected = row == self.session_index if key != -2 else False
            absolute = row  # already absolute index into entries

            def handler(
                mouse_event: MouseEvent, entry: int = absolute, selectable: int = key
            ) -> object:
                if mouse_event.event_type != MouseEventType.MOUSE_DOWN:
                    return None
                if selectable == -2:
                    self._set_focus("sessions")
                    return None
                self._set_focus("sessions")
                self._set_session(entry)
                with contextlib.suppress(Exception):
                    get_app().invalidate()
                return None

            self._append_entry(
                lines,
                focused=focused,
                selected=selected,
                title=title,
                subtitle=subtitle,
                mouse_handler=handler,
            )
        selectable = len([e for e in entries if e[0] != -2]) or len(entries)
        if selectable > capacity:
            lines.append(
                (
                    "class:frame.active.scroll" if focused else "class:frame.scroll",
                    f"  ↕ {start + 1}-{end}/{selectable}\n",
                )
            )
        return lines

    def _app_lines(self) -> StyleAndTextTuples:
        lines: StyleAndTextTuples = []
        focused = self.focus == "app"
        for index, app in enumerate(self.apps):
            selected = index == self.app_index
            row_focused = focused and selected
            style = self._row_style(focused=row_focused, selected=selected)
            marker = "● " if selected else "○ "
            badge_style = (
                f"class:badge.{app.style_key}.focused"
                if row_focused
                else f"class:badge.{app.style_key}"
            )

            def handler(mouse_event: MouseEvent, entry: int = index) -> object:
                if mouse_event.event_type != MouseEventType.MOUSE_DOWN:
                    return None
                self._set_focus("app")
                self._set_app(entry)
                with contextlib.suppress(Exception):
                    get_app().invalidate()
                return None

            lines.extend(
                [
                    (style, f" {marker}", handler),
                    (badge_style, f" {app.badge} ", handler),
                    (style, f" {app.display_name}\n", handler),
                ]
            )
        return lines

    def _provider_lines(self) -> StyleAndTextTuples:
        lines: StyleAndTextTuples = []
        providers = self.filtered_providers
        focused = self.focus == "provider"
        if not providers:
            msg = (
                f"(no matches: {self.provider_filter})"
                if self.provider_filter
                else "(no providers)"
            )
            lines.append(("class:item.muted", f"  {msg}\n"))
            return lines
        default_id = self.history.default_provider_id(self.current_app, self.all_app_providers)
        capacity = self._provider_capacity()
        start = max(0, min(self._provider_scroll, max(0, len(providers) - 1)))
        end = min(len(providers), start + capacity)
        for index in range(start, end):
            provider = providers[index]
            selected = index == self.provider_index
            display = display_configuration(provider)
            model = display.model or "no model"
            uses = self.history.usage(provider).launches
            mark = " · last" if provider.id == default_id else ""

            def handler(mouse_event: MouseEvent, entry: int = index) -> object:
                if mouse_event.event_type != MouseEventType.MOUSE_DOWN:
                    return None
                self._set_focus("provider")
                self.provider_index = entry
                self._sync_permission_selection()
                self._ensure_provider_visible()
                with contextlib.suppress(Exception):
                    get_app().invalidate()
                return None

            self._append_entry(
                lines,
                focused=focused,
                selected=selected,
                title=f"{provider.name}{mark}",
                subtitle=f"{model} · {uses} use{'s' if uses != 1 else ''}",
                mouse_handler=handler,
            )
        if len(providers) > capacity:
            lines.append(
                (
                    "class:frame.active.scroll" if focused else "class:frame.scroll",
                    f"  ↕ {start + 1}-{end}/{len(providers)}\n",
                )
            )
        return lines

    def _permission_lines(self) -> StyleAndTextTuples:
        lines: StyleAndTextTuples = []
        focused = self.focus == "permissions"
        for index, preset in enumerate(APPROVAL_PRESETS):
            selected = index == self.permission_index
            style = self._row_style(focused=focused and selected, selected=selected)
            sub_style = "class:item.focused-sub" if focused and selected else "class:item.muted"
            marker = "● " if selected else "○ "

            def handler(mouse_event: MouseEvent, entry: int = index) -> object:
                if mouse_event.event_type != MouseEventType.MOUSE_DOWN:
                    return None
                self._set_focus("permissions")
                self._set_permission(entry)
                with contextlib.suppress(Exception):
                    get_app().invalidate()
                return None

            lines.append((style, f" {marker}{preset.label}\n", handler))
            lines.append((sub_style, f"    {preset.description}\n", handler))
        return lines

    def _button_text(self) -> StyleAndTextTuples:
        focused = self.focus == "buttons"
        launch = (
            "class:button.launch.focused"
            if focused and self.button_index == 0
            else "class:button.launch"
        )
        cancel = (
            "class:button.cancel.focused"
            if focused and self.button_index == 1
            else "class:button.cancel"
        )
        return [
            (launch, "  ▶ Launch  "),
            ("", "   "),
            (cancel, "  ✕ Cancel  "),
            ("", "\n"),
        ]

    def _row_style(self, *, focused: bool, selected: bool) -> str:
        if focused:
            return "class:item.focused"
        if selected:
            return "class:item.selected"
        return "class:item"

    def _make_list_control(
        self,
        get_text: Callable[[], Any],
        pane: str,
        *,
        on_click_row: Callable[[int], None],
        on_scroll: Callable[[int], None],
    ) -> _ScrollListControl:
        return _ScrollListControl(
            get_text,
            on_click_row=on_click_row,
            on_scroll=on_scroll,
            on_activate=lambda: self._set_focus(pane),
        )

    def _build_application(self) -> None:
        session_control = self._make_list_control(
            lambda: FormattedText(self._session_lines()),
            "sessions",
            on_click_row=self._click_session,
            on_scroll=self._scroll_sessions,
        )
        app_control = self._make_list_control(
            lambda: FormattedText(self._app_lines()),
            "app",
            on_click_row=self._click_app,
            on_scroll=lambda d: self._navigate(d),
        )
        provider_control = self._make_list_control(
            lambda: FormattedText(self._provider_lines()),
            "provider",
            on_click_row=self._click_provider,
            on_scroll=self._scroll_providers,
        )
        permission_control = self._make_list_control(
            lambda: FormattedText(self._permission_lines()),
            "permissions",
            on_click_row=self._click_permission,
            on_scroll=lambda d: self._navigate(d),
        )

        def button_fragments() -> StyleAndTextTuples:
            focused = self.focus == "buttons"
            launch = (
                "class:button.launch.focused"
                if focused and self.button_index == 0
                else "class:button.launch"
            )
            cancel = (
                "class:button.cancel.focused"
                if focused and self.button_index == 1
                else "class:button.cancel"
            )

            def launch_handler(mouse_event: MouseEvent) -> object:
                if mouse_event.event_type != MouseEventType.MOUSE_DOWN:
                    return None
                self._set_focus("buttons")
                self.button_index = 0
                self._try_launch()
                return None

            def cancel_handler(mouse_event: MouseEvent) -> object:
                if mouse_event.event_type != MouseEventType.MOUSE_DOWN:
                    return None
                self._set_focus("buttons")
                self.button_index = 1
                self._cancel()
                return None

            return [
                (launch, "  ▶ Launch  ", launch_handler),
                ("", "   "),
                (cancel, "  ✕ Cancel  ", cancel_handler),
                ("", "\n"),
            ]

        button_control = FormattedTextControl(
            button_fragments,
            focusable=True,
            show_cursor=False,
        )

        self._sessions_window = Window(
            content=session_control,
            wrap_lines=False,
            always_hide_cursor=True,
            height=D(preferred=20, min=6),
        )
        self._app_window = Window(
            content=app_control, height=D(min=3, max=5), always_hide_cursor=True
        )
        self._provider_window = Window(
            content=provider_control,
            wrap_lines=False,
            always_hide_cursor=True,
            height=D(preferred=10, min=4),
        )
        self._permission_window = Window(
            content=permission_control,
            height=D(min=6, max=10),
            always_hide_cursor=True,
        )
        self._dir_window = Box(self.dir_area, padding_left=1, padding_right=1, height=1)
        self._buttons_window = Window(content=button_control, height=2, always_hide_cursor=True)

        left = HSplit(
            [
                self._highlighted_frame(self._app_window, "app", "app"),
                self._highlighted_frame(self._provider_window, "provider", "provider"),
                ConditionalContainer(
                    self._highlighted_frame(self._dir_window, "dir", "directory"),
                    filter=Condition(lambda: self.selected_session is None),
                ),
                ConditionalContainer(
                    self._highlighted_frame(self._permission_window, "permissions", "permissions"),
                    filter=Condition(lambda: self.current_app.supports_permission_overrides),
                ),
                Box(self._buttons_window, padding=1),
            ],
            padding=0,
            width=D(min=34, preferred=42),
        )
        sessions_frame = self._highlighted_frame(self._sessions_window, "sessions", "sessions")
        body = VSplit([left, sessions_frame], padding=1)

        root = HSplit(
            [
                Window(
                    FormattedTextControl(lambda: FormattedText(self._header_text())),
                    height=1,
                    style="class:header",
                ),
                body,
                self._focus_sink,
                Window(
                    FormattedTextControl(lambda: FormattedText(self._footer_text())),
                    height=1,
                    style="class:footer",
                    align=WindowAlign.LEFT,
                ),
            ],
            style="class:root",
        )
        self._root_container = root
        container: FloatContainer = FloatContainer(content=root, floats=[])
        bindings = self._key_bindings()
        self.application: Application[LaunchPlan | None] = Application(
            layout=Layout(container, focused_element=self._app_window),
            key_bindings=bindings,
            style=STYLE,
            mouse_support=True,
            full_screen=True,
        )

    # --- mouse handlers -----------------------------------------------

    def _click_session(self, row: int) -> None:
        # Windowed list: row is relative to the visible window, not absolute.
        entry = self._session_scroll + row // _SESSION_ROW
        max_index = self._session_entry_count() - 1
        if 0 <= entry <= max_index:
            self._set_session(entry)

    def _click_app(self, row: int) -> None:
        if 0 <= row < len(self.apps):
            self._set_app(row)

    def _click_provider(self, row: int) -> None:
        entry = self._provider_scroll + row // _PROVIDER_ROW
        providers = self.filtered_providers
        if 0 <= entry < len(providers):
            self.provider_index = entry
            self._sync_permission_selection()
            self._ensure_provider_visible()

    def _click_permission(self, row: int) -> None:
        entry = row // _PERMISSION_ROW
        if 0 <= entry < len(APPROVAL_PRESETS):
            self._set_permission(entry)

    def _set_permission(self, index: int) -> None:
        self.permission_index = max(0, min(index, len(APPROVAL_PRESETS) - 1))
        self.permission_override = True

    def _scroll_sessions(self, delta: int) -> None:
        self._set_focus("sessions")
        self._navigate(delta)

    def _scroll_providers(self, delta: int) -> None:
        self._set_focus("provider")
        self._navigate(delta)

    # --- keys ---------------------------------------------------------

    def _key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()
        list_nav = Condition(lambda: not self.filter_mode and self.focus != "dir")
        filtering = Condition(lambda: self.filter_mode)
        can_filter = Condition(
            lambda: not self.filter_mode and self.focus in {"provider", "sessions"}
        )

        @bindings.add("escape", eager=True)
        def _esc(event: Any) -> None:
            if self.filter_mode:
                self._clear_filter()
                return
            if self._active_filter():
                self._clear_filter()
                return
            event.app.exit(result=None)

        @bindings.add("c-c", eager=True)
        def _ctrl_c(event: Any) -> None:
            event.app.exit(result=None)

        @bindings.add("tab", eager=True)
        def _tab(event: Any) -> None:
            self._move_focus(1)

        @bindings.add("s-tab", eager=True)
        def _s_tab(event: Any) -> None:
            self._move_focus(-1)

        @bindings.add("down", filter=list_nav, eager=True)
        def _down(event: Any) -> None:
            self._navigate(1)

        @bindings.add("up", filter=list_nav, eager=True)
        def _up(event: Any) -> None:
            self._navigate(-1)

        @bindings.add("j", filter=list_nav, eager=True)
        def _j(event: Any) -> None:
            self._navigate(1)

        @bindings.add("k", filter=list_nav, eager=True)
        def _k(event: Any) -> None:
            self._navigate(-1)

        @bindings.add("right", filter=list_nav, eager=True)
        def _right(event: Any) -> None:
            if self.focus == "buttons":
                self.button_index = 1
            elif self.focus == "app":
                self._set_app(min(self.app_index + 1, len(self.apps) - 1))
            elif self.focus in {"sessions", "provider", "permissions"}:
                self._navigate(1)

        @bindings.add("left", filter=list_nav, eager=True)
        def _left(event: Any) -> None:
            if self.focus == "buttons":
                self.button_index = 0
            elif self.focus == "app":
                self._set_app(max(self.app_index - 1, 0))
            elif self.focus in {"sessions", "provider", "permissions"}:
                self._navigate(-1)

        @bindings.add("enter", eager=True)
        def _enter(event: Any) -> None:
            if self.filter_mode:
                self.filter_mode = False
                self._sync_layout_focus()
                return
            if self.focus == "buttons":
                if self.button_index == 0:
                    self._try_launch()
                else:
                    self._cancel()
            else:
                self._move_focus(1)

        @bindings.add("c-l", filter=list_nav, eager=True)
        def _launch_now(event: Any) -> None:
            self._try_launch()

        @bindings.add("pageup", filter=list_nav, eager=True)
        def _pgup(event: Any) -> None:
            self._navigate(-5)

        @bindings.add("pagedown", filter=list_nav, eager=True)
        def _pgdn(event: Any) -> None:
            self._navigate(5)

        @bindings.add("/", filter=can_filter, eager=True)
        def _slash(event: Any) -> None:
            self._start_filter()

        sessions_scope = Condition(lambda: self.focus == "sessions" and not self.filter_mode)

        @bindings.add("a", filter=sessions_scope, eager=True)
        def _toggle_scope(event: Any) -> None:
            self._toggle_sessions_scope()
            with contextlib.suppress(Exception):
                get_app().invalidate()

        @bindings.add("backspace", filter=filtering, eager=True)
        def _bs(event: Any) -> None:
            self._filter_backspace()

        @bindings.add("c-u", filter=filtering, eager=True)
        def _clear(event: Any) -> None:
            self._set_active_filter("")

        typing_start = Condition(
            lambda: not self.filter_mode and self.focus in {"provider", "sessions"}
        )

        # Bind printable characters explicitly. Never use eager ``<any>``:
        # it also matches Vt100MouseEvent and would swallow clicks/scroll.
        # 'a' on sessions (not filtering) is reserved for scope toggle above.
        _printable = (
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
            " -_.,:@+*=[]{}()!#$%^&;?~`'\"|<>"
        )
        for ch in _printable:

            @bindings.add(ch, filter=filtering, eager=True)
            def _filter_char(event: KeyPressEvent, char: str = ch) -> None:
                self._filter_append(char)

            if ch == "a":
                # Covered by sessions_scope toggle when focus is sessions.
                start_filter = Condition(lambda: not self.filter_mode and self.focus == "provider")
            else:
                start_filter = typing_start

            @bindings.add(ch, filter=start_filter, eager=True)
            def _start_char(event: KeyPressEvent, char: str = ch) -> None:
                if char.isdigit() and char != "0":
                    self._jump(int(char) - 1)
                    return
                if char in "jk":
                    self._navigate(1 if char == "j" else -1)
                    return
                self.filter_mode = True
                self._filter_append(char)
                self._sync_layout_focus()

        for digit in range(1, 10):

            @bindings.add(str(digit), filter=list_nav, eager=True)
            def _num(event: Any, n: int = digit) -> None:
                self._jump(n - 1)

        return bindings

    def _navigate(self, delta: int) -> None:
        if self.focus == "sessions":
            self._set_session(self.session_index + delta)
        elif self.focus == "app":
            self._set_app(max(0, min(self.app_index + delta, len(self.apps) - 1)))
        elif self.focus == "provider":
            providers = self.filtered_providers
            if providers:
                next_index = max(0, min(self.provider_index + delta, len(providers) - 1))
                if next_index != self.provider_index:
                    self.provider_index = next_index
                    self._sync_permission_selection()
                self._ensure_provider_visible()
        elif self.focus == "permissions":
            self._set_permission(self.permission_index + delta)
        elif self.focus == "buttons":
            self.button_index = 0 if delta < 0 else 1

    def _jump(self, index: int) -> None:
        if self.focus == "sessions":
            max_index = self._session_entry_count() - 1
            if 0 <= index <= max_index:
                self._set_session(index)
        elif self.focus == "app":
            if 0 <= index < len(self.apps):
                self._set_app(index)
        elif self.focus == "provider":
            providers = self.filtered_providers
            if 0 <= index < len(providers):
                if index != self.provider_index:
                    self.provider_index = index
                    self._sync_permission_selection()
                self._ensure_provider_visible()
        elif self.focus == "permissions":
            if 0 <= index < len(APPROVAL_PRESETS):
                self._set_permission(index)


def _relative_time(timestamp: float) -> str:
    try:
        delta = datetime.now().timestamp() - timestamp
    except (OverflowError, OSError, ValueError):
        return ""
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 86400 * 14:
        return f"{int(delta // 86400)}d ago"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def _short_path(path: str) -> str:
    if not path:
        return ""
    home = str(Path.home())
    text = path
    if text.startswith(home):
        text = "~" + text[len(home) :]
    if len(text) <= 40:
        return text
    return "…" + text[-39:]
