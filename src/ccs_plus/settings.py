from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from dynaconf import Dynaconf

from ccs_plus.domain import ProviderError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENCRYPTION_KEY_EXAMPLE = "replace-with-a-fernet-key"


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    database_path: Path
    claude_home: Path
    codex_home: Path
    grok_home: Path
    encryption_key: str

    def state_home(self, app: str) -> Path:
        values = {
            "claude": self.claude_home,
            "codex": self.codex_home,
            "grok": self.grok_home,
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


def load_settings(project_root: Path | None = None) -> AppSettings:
    root = (project_root or PROJECT_ROOT).resolve()
    load_dotenv(root / ".env", override=False)
    config = Dynaconf(
        envvar_prefix="CCS_PLUS",
        settings_files=[str(root / "settings.toml")],
        # The checked-in settings file uses Dynaconf's [default] environment.
        # Restricting settings_files also keeps .secrets.toml out of the load path.
        environments=True,
        merge_enabled=True,
    )
    return AppSettings(
        project_root=root,
        database_path=_resolve_path(root, config.get("DATABASE_PATH"), "DATABASE_PATH"),
        claude_home=_resolve_path(root, config.get("CLAUDE_HOME"), "CLAUDE_HOME"),
        codex_home=_resolve_path(root, config.get("CODEX_HOME"), "CODEX_HOME"),
        grok_home=_resolve_path(root, config.get("GROK_HOME"), "GROK_HOME"),
        encryption_key=_resolve_encryption_key(config.get("ENCRYPTION_KEY"), "ENCRYPTION_KEY"),
    )


def environment_with_defaults() -> dict[str, str]:
    return dict(os.environ)
