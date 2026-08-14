from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urlparse

if TYPE_CHECKING:
    from ccs_plus.settings import AppSettings


class ProviderError(Exception):
    """A user-facing provider or launcher error."""


class AppKind(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"
    GROK = "grok"

    @property
    def db_app_type(self) -> str:
        return "grokbuild" if self is AppKind.GROK else self.value

    @property
    def executable(self) -> str:
        return self.value

    @property
    def supports_permission_overrides(self) -> bool:
        return self is AppKind.CODEX

    @property
    def has_managed_profile_files(self) -> bool:
        return self is AppKind.CODEX

    @property
    def display_name(self) -> str:
        """Human-facing label for TUI / tables (Title Case)."""
        return {
            AppKind.CLAUDE: "Claude",
            AppKind.CODEX: "Codex",
            AppKind.GROK: "Grok",
        }[self]

    @property
    def badge(self) -> str:
        """Short terminal-safe badge shown beside the display name."""
        return {
            AppKind.CLAUDE: "Cl",
            AppKind.CODEX: "Cx",
            AppKind.GROK: "Gk",
        }[self]

    @property
    def style_key(self) -> str:
        """prompt_toolkit style class suffix for this app's badge color."""
        return self.value

    @classmethod
    def from_cli_value(cls, value: str) -> AppKind:
        try:
            return cls(value.lower())
        except ValueError as exc:
            raise ProviderError(f"Unsupported application: {value}") from exc


OFFICIAL_PROVIDER_IDS = {
    "claude-official",
    "codex-official",
    "grokbuild-official",
}


EFFORTS: dict[AppKind, set[str]] = {
    AppKind.CLAUDE: {"low", "medium", "high", "xhigh", "max"},
    AppKind.CODEX: {"minimal", "low", "medium", "high", "xhigh"},
}


@dataclass(frozen=True)
class Provider:
    id: str
    app: AppKind
    name: str
    settings_config: dict[str, Any]
    endpoints: tuple[str, ...]
    category: str | None
    created_at: int | None
    notes: str | None
    is_current: bool
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_official(self) -> bool:
        return self.id in OFFICIAL_PROVIDER_IDS or self.category == "official"


@dataclass(frozen=True)
class NewProvider:
    app: AppKind
    name: str
    endpoint: str
    api_key: str
    model: str
    effort: str | None
    notes: str | None


@dataclass(frozen=True)
class CodexAppConfig:
    """Defaults used when creating Codex providers (add/import)."""

    approval_policy: str
    sandbox_mode: str


@dataclass(frozen=True)
class RuntimeProvider:
    """Common connection and model data shared by every native CLI."""

    provider: Provider
    endpoint: str | None
    api_key: str | None
    model: str | None
    effort: str | None

    def permission_overrides(self) -> tuple[str | None, str | None]:
        return None, None

    def with_permission_defaults(self, settings: AppSettings) -> Self:
        return self

    def with_permission_override(
        self,
        approval_policy: str | None,
        sandbox_mode: str | None,
    ) -> Self:
        if approval_policy is not None or sandbox_mode is not None:
            raise ProviderError("Permission overrides are not supported for this runtime.")
        return self


@dataclass(frozen=True)
class ClaudeRuntime(RuntimeProvider):
    """Claude-specific environment and permission settings."""

    claude_env: dict[str, str] = field(default_factory=dict)
    permission_mode: str | None = None

    def with_permission_defaults(self, settings: AppSettings) -> Self:
        return replace(
            self,
            permission_mode=self.permission_mode or settings.claude.permission_mode,
        )


@dataclass(frozen=True)
class CodexRuntime(RuntimeProvider):
    """Codex-specific permission settings."""

    approval_policy: str | None = None
    sandbox_mode: str | None = None

    def permission_overrides(self) -> tuple[str | None, str | None]:
        return self.approval_policy, self.sandbox_mode

    def with_permission_defaults(self, settings: AppSettings) -> Self:
        return replace(
            self,
            approval_policy=self.approval_policy or settings.codex.approval_policy,
            sandbox_mode=self.sandbox_mode or settings.codex.sandbox_mode,
        )

    def with_permission_override(
        self,
        approval_policy: str | None,
        sandbox_mode: str | None,
    ) -> Self:
        return replace(
            self,
            approval_policy=(
                approval_policy if approval_policy is not None else self.approval_policy
            ),
            sandbox_mode=sandbox_mode if sandbox_mode is not None else self.sandbox_mode,
        )


@dataclass(frozen=True)
class GrokRuntime(RuntimeProvider):
    """Grok-specific sandbox and approval settings."""

    sandbox_mode: str | None = None
    always_approve: bool | None = None

    def with_permission_defaults(self, settings: AppSettings) -> Self:
        return replace(
            self,
            sandbox_mode=self.sandbox_mode or settings.grok.sandbox_mode,
            always_approve=(
                settings.grok.always_approve if self.always_approve is None else self.always_approve
            ),
        )


RuntimeConfig = ClaudeRuntime | CodexRuntime | GrokRuntime


@dataclass(frozen=True)
class ProviderDisplay:
    endpoint: str | None
    model: str | None
    effort: str | None


def validate_new_provider(value: NewProvider) -> None:
    if not value.name.strip():
        raise ProviderError("Provider name cannot be empty.")
    if not value.api_key.strip():
        raise ProviderError("API Key cannot be empty.")
    if not value.model.strip():
        raise ProviderError("Model cannot be empty.")

    parsed = urlparse(value.endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderError("Endpoint must be an absolute http or https URL.")

    if value.effort:
        validate_effort(value.app, value.effort)


def validate_launch_options(app: AppKind, model: str | None, effort: str | None) -> None:
    if model is not None and not model.strip():
        raise ProviderError("Model cannot be empty.")
    if effort is not None:
        validate_effort(app, effort)


def validate_effort(app: AppKind, effort: str) -> None:
    normalized = effort.strip()
    if not normalized:
        raise ProviderError("Reasoning effort cannot be empty.")
    allowed = EFFORTS.get(app)
    if allowed and normalized not in allowed:
        values = ", ".join(sorted(allowed))
        raise ProviderError(f"Invalid {app.value} effort. Expected one of: {values}.")


def redact(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
