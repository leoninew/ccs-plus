from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ccs_plus.adapters import runtime_from_provider
from ccs_plus.domain import (
    ClaudeRuntime,
    CodexRuntime,
    GrokRuntime,
    OpenCodeRuntime,
    Provider,
    ProviderError,
    RuntimeConfig,
    validate_launch_options,
)
from ccs_plus.home_visibility import home_visibility_for
from ccs_plus.managed_config import ensure_managed_config
from ccs_plus.sessions import Session
from ccs_plus.settings import AppSettings, environment_with_defaults

logger = logging.getLogger(__name__)
PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]


@dataclass(frozen=True)
class RuntimeLauncher:
    executable: str
    env: dict[str, str]
    runtime_home: Path
    model: str | None
    effort: str | None
    session_id: str | None

    def build(self) -> list[str]:
        raise NotImplementedError


@dataclass(frozen=True)
class ClaudeLauncher(RuntimeLauncher):
    runtime: ClaudeRuntime
    permission_mode: str

    def build(self) -> list[str]:
        _clear(self.env, "CLAUDE_CONFIG_DIR")
        self.env["CLAUDE_CONFIG_DIR"] = str(self.runtime_home)
        _clear(
            self.env,
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "CLAUDE_CODE_EFFORT_LEVEL",
        )
        managed = None if self.runtime.provider.is_official else self.runtime
        if managed is not None:
            self.env.update(managed.claude_env)
            if self.model:
                for key in (
                    "ANTHROPIC_MODEL",
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                    "ANTHROPIC_DEFAULT_SONNET_MODEL",
                    "ANTHROPIC_DEFAULT_OPUS_MODEL",
                ):
                    self.env[key] = self.model
            if self.effort:
                self.env["CLAUDE_CODE_EFFORT_LEVEL"] = self.effort
        argv = [self.executable]
        if self.session_id:
            argv.extend(["--resume", self.session_id])
        if managed is None and self.model:
            argv.extend(["--model", self.model])
        if self.effort:
            argv.extend(["--effort", self.effort])
        argv.extend(["--permission-mode", self.permission_mode])
        return argv


@dataclass(frozen=True)
class CodexLauncher(RuntimeLauncher):
    runtime: CodexRuntime
    session_model_provider: str
    approval_policy: str
    sandbox_mode: str

    def build(self) -> list[str]:
        _clear(self.env, "CODEX_HOME", "CODEX_SQLITE_HOME")
        self.env["CODEX_HOME"] = str(self.runtime_home)
        argv = [self.executable]
        if self.session_id:
            argv.extend(["resume", self.session_id])
        managed = None if self.runtime.provider.is_official else self.runtime
        if managed is not None:
            profile = ensure_managed_config(
                managed,
                self.runtime_home,
                self.model,
                self.effort,
                session_model_provider=self.session_model_provider,
                approval_policy=self.approval_policy,
                sandbox_mode=self.sandbox_mode,
            )
            self.env[profile.env_key] = _required(managed.api_key, "Codex API key")
            argv.extend(["--profile", profile.name])
            # Managed API-key providers do not need the ChatGPT-backed Codex Apps MCP.
            argv.extend(["--disable", "apps"])
            self._append_model_and_effort(argv)
            return argv
        if not self.session_id:
            self._append_model_and_effort(argv)
        argv.extend(["--ask-for-approval", self.approval_policy])
        return argv

    def _append_model_and_effort(self, argv: list[str]) -> None:
        if self.model:
            argv.extend(["--model", self.model])
        if self.effort:
            argv.extend(["-c", f"model_reasoning_effort={self.effort}"])


@dataclass(frozen=True)
class GrokLauncher(RuntimeLauncher):
    runtime: GrokRuntime
    sandbox_mode: str
    always_approve: bool

    def build(self) -> list[str]:
        _clear(self.env, "GROK_HOME", "GROK_MODELS_BASE_URL", "GROK_MODELS_LIST_URL")
        self.env["GROK_HOME"] = str(self.runtime_home)
        argv = [self.executable]
        if self.session_id:
            argv.extend(["--resume", self.session_id])
        managed = None if self.runtime.provider.is_official else self.runtime
        if managed is not None:
            profile = ensure_managed_config(managed, self.runtime_home, self.model, self.effort)
            self.env[profile.env_key] = _required(managed.api_key, "Grok API key")
            argv.extend(["--model", profile.name])
        elif self.model:
            argv.extend(["--model", self.model])
        if self.effort:
            argv.extend(["--reasoning-effort", self.effort])
        argv.extend(["--sandbox", self.sandbox_mode])
        if self.always_approve:
            argv.append("--always-approve")
        return argv


@dataclass(frozen=True)
class OpenCodeLauncher(RuntimeLauncher):
    runtime: OpenCodeRuntime
    permission_mode: str
    always_approve: bool

    def build(self) -> list[str]:
        # OpenCode resolves config/data via XDG; isolate under runtime_home.
        data_home = self.runtime_home / "share"
        config_home = self.runtime_home / "config"
        data_home.mkdir(parents=True, exist_ok=True)
        config_home.mkdir(parents=True, exist_ok=True)
        _clear(
            self.env,
            "XDG_DATA_HOME",
            "XDG_CONFIG_HOME",
            "OPENCODE_CONFIG",
            "OPENCODE_CONFIG_CONTENT",
            "OPENCODE_CONFIG_DIR",
        )
        self.env["XDG_DATA_HOME"] = str(data_home)
        self.env["XDG_CONFIG_HOME"] = str(config_home)

        managed = None if self.runtime.provider.is_official else self.runtime
        if managed is not None:
            content = _opencode_config_content(
                managed,
                model=self.model,
                effort=self.effort,
                permission_mode=self.permission_mode,
            )
            self.env["OPENCODE_CONFIG_CONTENT"] = content
        else:
            # Official / local auth: only inject permission override.
            self.env["OPENCODE_CONFIG_CONTENT"] = _opencode_permission_content(self.permission_mode)

        argv = [self.executable]
        if self.session_id:
            argv.extend(["--session", self.session_id])
        if managed is None and self.model:
            argv.extend(["--model", self.model])
        if self.effort:
            argv.extend(["--variant", self.effort])
        if self.always_approve:
            argv.append("--auto")
        return argv


def _opencode_permission_content(permission_mode: str) -> str:
    import json

    return json.dumps({"permission": permission_mode}, separators=(",", ":"))


def _opencode_config_content(
    runtime: OpenCodeRuntime,
    *,
    model: str | None,
    effort: str | None,
    permission_mode: str,
) -> str:
    import json

    model_ref = model or runtime.model or ""
    provider_id = "custom"
    model_id = model_ref
    if "/" in model_ref:
        provider_id, model_id = model_ref.split("/", 1)
    endpoint = _required(runtime.endpoint, "OpenCode endpoint")
    api_key = _required(runtime.api_key, "OpenCode API key")
    document: dict[str, object] = {
        "model": f"{provider_id}/{model_id}",
        "permission": permission_mode,
        "provider": {
            provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "options": {
                    "apiKey": api_key,
                    "baseURL": endpoint,
                },
                "models": {
                    model_id: {
                        "name": model_id,
                    }
                },
            }
        },
    }
    del effort  # variant is passed on CLI when set
    return json.dumps(document, separators=(",", ":"))


def build_launch_spec(
    provider: Provider,
    settings: AppSettings,
    cwd: Path | None = None,
    model_override: str | None = None,
    effort_override: str | None = None,
    *,
    resume: Session | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    permission_mode: str | None = None,
    always_approve: bool | None = None,
) -> LaunchSpec:
    if resume is not None and resume.app is not provider.app:
        raise ProviderError(
            f"Session app {resume.app.value} does not match provider app {provider.app.value}."
        )
    if resume is not None and resume.cwd:
        working_directory = Path(resume.cwd).expanduser()
        if not working_directory.is_absolute():
            working_directory = (Path.cwd() / working_directory).resolve()
        else:
            working_directory = working_directory.resolve()
    else:
        working_directory = (cwd or Path.cwd()).resolve()
    if not working_directory.is_dir():
        raise ProviderError(f"Working directory does not exist: {working_directory}")
    validate_launch_options(provider.app, model_override, effort_override)
    executable = shutil.which(provider.app.executable)
    if not executable:
        raise ProviderError(f"{provider.app.executable} CLI was not found on PATH.")

    runtime = runtime_from_provider(provider).with_permission_defaults(settings)
    if (
        approval_policy is not None
        or sandbox_mode is not None
        or permission_mode is not None
        or always_approve is not None
    ):
        runtime = runtime.with_permission_override(
            approval_policy,
            sandbox_mode,
            permission_mode=permission_mode,
            always_approve=always_approve,
        )
    env = environment_with_defaults()
    _apply_proxy(env, settings.proxy)
    runtime_home = settings.runtime_home(provider.app.value)
    if not isinstance(runtime, CodexRuntime):
        visibility = home_visibility_for(
            runtime,
            settings,
            runtime_home,
            enabled=not (
                isinstance(runtime, OpenCodeRuntime) and _is_user_home_directory(working_directory)
            ),
        )
        visibility.apply()
    model = model_override or runtime.model
    effort = effort_override or runtime.effort
    session_id = resume.session_id if resume is not None else None

    launcher = runtime_launcher_for(
        runtime,
        executable=executable,
        env=env,
        runtime_home=runtime_home,
        model=model,
        effort=effort,
        session_id=session_id,
        settings=settings,
    )
    argv = launcher.build()
    return LaunchSpec(argv=tuple(argv), cwd=working_directory, env=env)


def runtime_launcher_for(
    runtime: RuntimeConfig,
    *,
    executable: str,
    env: dict[str, str],
    runtime_home: Path,
    model: str | None,
    effort: str | None,
    session_id: str | None,
    settings: AppSettings,
) -> RuntimeLauncher:
    if isinstance(runtime, ClaudeRuntime):
        return ClaudeLauncher(
            executable=executable,
            env=env,
            runtime_home=runtime_home,
            model=model,
            effort=effort,
            session_id=session_id,
            runtime=runtime,
            permission_mode=_required(runtime.permission_mode, "Claude permission_mode"),
        )
    if isinstance(runtime, CodexRuntime):
        return CodexLauncher(
            executable=executable,
            env=env,
            runtime_home=runtime_home,
            model=model,
            effort=effort,
            session_id=session_id,
            runtime=runtime,
            session_model_provider=settings.codex.session_model_provider,
            approval_policy=_required(runtime.approval_policy, "Codex approval_policy"),
            sandbox_mode=_required(runtime.sandbox_mode, "Codex sandbox_mode"),
        )
    if isinstance(runtime, GrokRuntime):
        return GrokLauncher(
            executable=executable,
            env=env,
            runtime_home=runtime_home,
            model=model,
            effort=effort,
            session_id=session_id,
            runtime=runtime,
            sandbox_mode=_required(runtime.sandbox_mode, "Grok sandbox_mode"),
            always_approve=_required_bool(runtime.always_approve, "Grok always_approve"),
        )
    if isinstance(runtime, OpenCodeRuntime):
        return OpenCodeLauncher(
            executable=executable,
            env=env,
            runtime_home=runtime_home,
            model=model,
            effort=effort,
            session_id=session_id,
            runtime=runtime,
            permission_mode=_required(runtime.permission_mode, "OpenCode permission_mode"),
            always_approve=_required_bool(runtime.always_approve, "OpenCode always_approve"),
        )
    raise ProviderError(f"Unsupported runtime: {type(runtime).__name__}.")


def launch(spec: LaunchSpec) -> int:
    logger.info("Starting native CLI in %s with argv=%r", spec.cwd, spec.argv)
    completed = subprocess.run(list(spec.argv), cwd=spec.cwd, env=spec.env, check=False)
    logger.info("Native CLI exited with code %s", completed.returncode)
    return completed.returncode


def _required(value: str | None, label: str) -> str:
    if not value:
        raise ProviderError(f"{label} is missing from cc-switch settings_config.")
    return value


def _required_bool(value: bool | None, label: str) -> bool:
    if value is None:
        raise ProviderError(f"{label} is missing from cc-switch settings_config.")
    return value


def _clear(env: dict[str, str], *keys: str) -> None:
    for key in keys:
        env.pop(key, None)


def _apply_proxy(env: dict[str, str], proxy: str) -> None:
    for key in PROXY_ENV_KEYS:
        env[key] = proxy


def _is_user_home_directory(path: Path, user_home: Path | None = None) -> bool:
    """Return whether *path* is the operating-system user Home itself."""
    home = user_home or Path.home()
    return os.path.normcase(os.fspath(path.resolve())) == os.path.normcase(
        os.fspath(home.resolve())
    )
