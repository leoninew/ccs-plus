from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from ccs_plus.adapters import runtime_from_provider
from ccs_plus.domain import (
    ClaudeRuntime,
    CodexRuntime,
    GrokRuntime,
    Provider,
    ProviderError,
    RuntimeConfig,
    validate_launch_options,
)
from ccs_plus.home_visibility import apply_claude_visibility, apply_codex_visibility
from ccs_plus.managed_config import ensure_managed_config, sync_codex_user_config
from ccs_plus.sessions import Session
from ccs_plus.settings import AppSettings, environment_with_defaults

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]


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

    runtime = _runtime_with_permission_defaults(runtime_from_provider(provider), settings)
    # TUI exposes permission overrides only for Codex.
    if approval_policy is not None or sandbox_mode is not None:
        if not isinstance(runtime, CodexRuntime):
            raise ProviderError("Permission overrides are only supported for Codex.")
        runtime = replace(
            runtime,
            approval_policy=approval_policy
            if approval_policy is not None
            else runtime.approval_policy,
            sandbox_mode=sandbox_mode if sandbox_mode is not None else runtime.sandbox_mode,
        )
    env = environment_with_defaults()
    state_home = settings.state_home(provider.app.value)
    model = model_override or runtime.model
    effort = effort_override or runtime.effort
    session_id = resume.session_id if resume is not None else None

    if isinstance(runtime, ClaudeRuntime):
        if settings.claude.user_home is not None:
            apply_claude_visibility(state_home, settings.claude.user_home)
        argv = _claude_spec(
            executable,
            runtime,
            env,
            state_home,
            model,
            effort,
            _required(runtime.permission_mode, "Claude permission_mode"),
            session_id=session_id,
        )
    elif isinstance(runtime, CodexRuntime):
        apply_codex_visibility(state_home, settings.codex.user_home)
        argv = _codex_spec(
            executable,
            runtime,
            env,
            state_home,
            model=model,
            effort=effort,
            user_home=settings.codex.user_home,
            session_model_provider=settings.codex.session_model_provider,
            project_directory=working_directory,
            approval_policy=runtime.approval_policy,
            sandbox_mode=runtime.sandbox_mode,
            session_id=session_id,
        )
    elif isinstance(runtime, GrokRuntime):
        argv = _grok_spec(
            executable,
            runtime,
            env,
            state_home,
            model,
            effort,
            _required(runtime.sandbox_mode, "Grok sandbox_mode"),
            _required_bool(runtime.always_approve, "Grok always_approve"),
            session_id=session_id,
        )
    else:
        raise ProviderError(f"Unsupported runtime for {provider.app.value}.")
    return LaunchSpec(argv=tuple(argv), cwd=working_directory, env=env)


def launch(spec: LaunchSpec) -> int:
    logger.info("Starting native CLI in %s with argv=%r", spec.cwd, spec.argv)
    completed = subprocess.run(list(spec.argv), cwd=spec.cwd, env=spec.env, check=False)
    logger.info("Native CLI exited with code %s", completed.returncode)
    return completed.returncode


def _claude_spec(
    executable: str,
    runtime: ClaudeRuntime,
    env: dict[str, str],
    state_home: Path,
    model: str | None,
    effort: str | None,
    permission_mode: str,
    *,
    session_id: str | None = None,
) -> list[str]:
    _clear(env, "CLAUDE_CONFIG_DIR")
    env["CLAUDE_CONFIG_DIR"] = str(state_home)
    _clear(
        env,
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "CLAUDE_CODE_EFFORT_LEVEL",
    )
    runtime_provider = None if runtime.provider.is_official else runtime
    if runtime_provider is not None:
        env.update(runtime_provider.claude_env)
        if model:
            for key in (
                "ANTHROPIC_MODEL",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                "ANTHROPIC_DEFAULT_SONNET_MODEL",
                "ANTHROPIC_DEFAULT_OPUS_MODEL",
            ):
                env[key] = model
        if effort:
            env["CLAUDE_CODE_EFFORT_LEVEL"] = effort
    argv = [executable]
    if session_id:
        argv.extend(["--resume", session_id])
    if runtime_provider is None and model:
        argv.extend(["--model", model])
    # Official Claude takes --effort; custom also gets it so session sticky UI cannot
    # ignore CLAUDE_CODE_EFFORT_LEVEL / provider effortLevel.
    if effort:
        argv.extend(["--effort", effort])
    argv.extend(["--permission-mode", permission_mode])
    return argv


def _codex_spec(
    executable: str,
    runtime: CodexRuntime,
    env: dict[str, str],
    state_home: Path,
    model: str | None,
    effort: str | None,
    user_home: Path | None = None,
    session_model_provider: str | None = None,
    project_directory: Path | None = None,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    session_id: str | None = None,
) -> list[str]:
    _clear(env, "CODEX_HOME", "CODEX_SQLITE_HOME")
    env["CODEX_HOME"] = str(state_home)
    argv = [executable]
    if session_id:
        argv.extend(["resume", session_id])
    runtime_provider = None if runtime.provider.is_official else runtime
    if runtime_provider is not None:
        profile = ensure_managed_config(
            runtime_provider,
            state_home,
            model,
            effort,
            user_home=user_home,
            session_model_provider=session_model_provider,
            project_directory=project_directory,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
        )
        env[profile.env_key] = _required(runtime_provider.api_key, "Codex API key")
        argv.extend(["--profile", profile.name])
        # Profile holds provider endpoint/auth/permissions. Also pass model/effort on
        # argv so Codex does not keep sticky collaboration-mode defaults.
        _append_codex_model_and_effort(argv, model=model, effort=effort)
        return argv
    if user_home is not None:
        sync_codex_user_config(state_home, user_home, project_directory)
    if not session_id:
        _append_codex_model_and_effort(argv, model=model, effort=effort)
    argv.extend(["--ask-for-approval", _required(runtime.approval_policy, "Codex approval_policy")])
    return argv


def _append_codex_model_and_effort(
    argv: list[str],
    *,
    model: str | None,
    effort: str | None,
) -> None:
    """Codex has --model, but effort is only a config key (no dedicated flag)."""
    if model:
        argv.extend(["--model", model])
    if effort:
        # -c values are parsed as TOML; bare tokens are strings.
        argv.extend(["-c", f"model_reasoning_effort={effort}"])


def _grok_spec(
    executable: str,
    runtime: GrokRuntime,
    env: dict[str, str],
    state_home: Path,
    model: str | None,
    effort: str | None,
    sandbox_mode: str,
    always_approve: bool,
    *,
    session_id: str | None = None,
) -> list[str]:
    _clear(env, "GROK_HOME", "GROK_MODELS_BASE_URL", "GROK_MODELS_LIST_URL")
    env["GROK_HOME"] = str(state_home)
    argv = [executable]
    if session_id:
        argv.extend(["--resume", session_id])
    runtime_provider = None if runtime.provider.is_official else runtime
    if runtime_provider is not None:
        profile = ensure_managed_config(runtime_provider, state_home, model, effort)
        env[profile.env_key] = _required(runtime_provider.api_key, "Grok API key")
        # --model selects the managed profile name; API model id lives in config.
        argv.extend(["--model", profile.name])
    elif model:
        argv.extend(["--model", model])
    # Prefer CLI over [models].default_reasoning_effort so provider/override wins.
    if effort:
        argv.extend(["--reasoning-effort", effort])
    argv.extend(["--sandbox", sandbox_mode])
    if always_approve:
        argv.append("--always-approve")
    return argv


def _runtime_with_permission_defaults(
    runtime: RuntimeConfig,
    settings: AppSettings,
) -> RuntimeConfig:
    """Use app settings only for permission values absent from a provider record."""
    if isinstance(runtime, ClaudeRuntime):
        return replace(
            runtime,
            permission_mode=runtime.permission_mode or settings.claude.permission_mode,
        )
    if isinstance(runtime, CodexRuntime):
        return replace(
            runtime,
            approval_policy=runtime.approval_policy or settings.codex.approval_policy,
            sandbox_mode=runtime.sandbox_mode or settings.codex.sandbox_mode,
        )
    return replace(
        runtime,
        sandbox_mode=runtime.sandbox_mode or settings.grok.sandbox_mode,
        always_approve=(
            settings.grok.always_approve
            if runtime.always_approve is None
            else runtime.always_approve
        ),
    )


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
