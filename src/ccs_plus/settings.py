from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from dynaconf import Dynaconf

from ccs_plus.domain import CodexAppConfig, ProviderError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENCRYPTION_KEY_EXAMPLE = "replace-with-a-fernet-key"
SETTINGS_FILE = "settings.yaml"


@dataclass(frozen=True)
class AppHomeSettings:
    home: Path
    user_home: Path | None = None


@dataclass(frozen=True)
class ClaudeSettings:
    home: Path
    permission_mode: str
    user_home: Path | None = None


@dataclass(frozen=True)
class GrokSettings:
    home: Path
    sandbox_mode: str
    always_approve: bool
    user_home: Path | None = None


@dataclass(frozen=True)
class CodexSettings:
    home: Path
    user_home: Path
    session_model_provider: str
    approval_policy: str
    sandbox_mode: str

    def provider_defaults(self) -> CodexAppConfig:
        return CodexAppConfig(
            approval_policy=self.approval_policy,
            sandbox_mode=self.sandbox_mode,
        )


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    database_path: Path
    encryption_key: str
    proxy: str
    claude: ClaudeSettings
    codex: CodexSettings
    grok: GrokSettings

    def state_home(self, app: str) -> Path:
        values = {
            "claude": self.claude.home,
            "codex": self.codex.home,
            "grok": self.grok.home,
        }
        try:
            return values[app]
        except KeyError as exc:
            raise ProviderError(f"Unsupported state home: {app}") from exc


def _resolve_path(root: Path, value: object, key: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError(f"Configuration {key} must be a non-empty path.")
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


def _default_user_home(name: str) -> Path:
    """Built-in real CLI home: ``Path.home() / name`` (e.g. ``.claude``, ``.codex``)."""
    return Path.home() / name


def _resolve_optional_user_home(root: Path, value: object, key: str, default_name: str) -> Path:
    """Optional override for real user home.

    When the key is absent or blank, use ``Path.home() / default_name``.
    Only an explicitly provided non-empty value overrides that default.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return _default_user_home(default_name)
    return _resolve_path(root, value, key)


def _resolve_encryption_key(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError(f"Configuration {key} must be a non-empty Fernet key.")
    if value == ENCRYPTION_KEY_EXAMPLE:
        raise ProviderError(f"Configuration {key} must replace the example key.")
    try:
        Fernet(value.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise ProviderError(f"Configuration {key} must be a valid Fernet key.") from exc
    return value


def _resolve_non_empty_string(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError(f"Configuration {key} must be a non-empty string.")
    return value.strip()


def _resolve_proxy(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProviderError("Configuration proxy must be a string.")
    return value.strip()


def _resolve_bool(value: object, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ProviderError(f"Configuration {key} must be a boolean.")


def _get(config: Dynaconf, key: str) -> object:
    return config.get(key)


def load_settings(project_root: Path | None = None) -> AppSettings:
    root = (project_root or PROJECT_ROOT).resolve()
    load_dotenv(root / ".env", override=False)
    settings_path = root / SETTINGS_FILE
    if not settings_path.is_file():
        raise ProviderError(f"Configuration file is missing: {settings_path}")
    config = Dynaconf(
        envvar_prefix="CCS_PLUS",
        settings_files=[str(settings_path)],
        # No Dynaconf environment layer — YAML is the source schema.
        # Restricting settings_files keeps .secrets.* out of the load path.
        environments=False,
        merge_enabled=True,
    )
    return AppSettings(
        project_root=root,
        database_path=_resolve_path(root, _get(config, "database.path"), "database.path"),
        encryption_key=_resolve_encryption_key(_get(config, "encryption_key"), "encryption_key"),
        proxy=_resolve_proxy(_get(config, "proxy")),
        claude=ClaudeSettings(
            home=_resolve_path(root, _get(config, "apps.claude.home"), "apps.claude.home"),
            user_home=_resolve_optional_user_home(
                root,
                _get(config, "apps.claude.user_home"),
                "apps.claude.user_home",
                ".claude",
            ),
            permission_mode=_resolve_non_empty_string(
                _get(config, "apps.claude.permission_mode"),
                "apps.claude.permission_mode",
            ),
        ),
        codex=CodexSettings(
            home=_resolve_path(root, _get(config, "apps.codex.home"), "apps.codex.home"),
            user_home=_resolve_optional_user_home(
                root,
                _get(config, "apps.codex.user_home"),
                "apps.codex.user_home",
                ".codex",
            ),
            session_model_provider=_resolve_non_empty_string(
                _get(config, "apps.codex.session_model_provider"),
                "apps.codex.session_model_provider",
            ),
            approval_policy=_resolve_non_empty_string(
                _get(config, "apps.codex.approval_policy"),
                "apps.codex.approval_policy",
            ),
            sandbox_mode=_resolve_non_empty_string(
                _get(config, "apps.codex.sandbox_mode"),
                "apps.codex.sandbox_mode",
            ),
        ),
        grok=GrokSettings(
            home=_resolve_path(root, _get(config, "apps.grok.home"), "apps.grok.home"),
            sandbox_mode=_resolve_non_empty_string(
                _get(config, "apps.grok.sandbox_mode"),
                "apps.grok.sandbox_mode",
            ),
            always_approve=_resolve_bool(
                _get(config, "apps.grok.always_approve"),
                "apps.grok.always_approve",
            ),
        ),
    )


def environment_with_defaults() -> dict[str, str]:
    return dict(os.environ)
