from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from ccs_plus.adapters import runtime_from_provider
from ccs_plus.domain import (
    AppKind,
    Provider,
    ProviderError,
    RuntimeProvider,
    validate_launch_options,
)
from ccs_plus.home_visibility import apply_claude_visibility, apply_codex_visibility
from ccs_plus.managed_config import ensure_managed_config, sync_codex_user_config
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
) -> LaunchSpec:
    working_directory = (cwd or Path.cwd()).resolve()
    if not working_directory.is_dir():
        raise ProviderError(f"Working directory does not exist: {working_directory}")
    validate_launch_options(provider.app, model_override, effort_override)
    executable = shutil.which(provider.app.executable)
    if not executable:
        raise ProviderError(f"{provider.app.executable} CLI was not found on PATH.")

    runtime = _runtime_with_permission_defaults(runtime_from_provider(provider), settings)
    env = environment_with_defaults()
    state_home = settings.state_home(provider.app.value)
    model = model_override or runtime.model
    effort = effort_override or runtime.effort

    if provider.app is AppKind.CLAUDE:
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
        )
    elif provider.app is AppKind.CODEX:
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
        )
    else:
        argv = _grok_spec(
            executable,
            runtime,
            env,
            state_home,
            model,
            effort,
            _required(runtime.sandbox_mode, "Grok sandbox_mode"),
            _required_bool(runtime.always_approve, "Grok always_approve"),
        )
    return LaunchSpec(argv=tuple(argv), cwd=working_directory, env=env)


def launch(spec: LaunchSpec) -> int:
    logger.info("Starting native CLI in %s with argv=%r", spec.cwd, spec.argv)
    completed = subprocess.run(list(spec.argv), cwd=spec.cwd, env=spec.env, check=False)
    logger.info("Native CLI exited with code %s", completed.returncode)
    return completed.returncode


def _claude_spec(
    executable: str,
    runtime: RuntimeProvider,
    env: dict[str, str],
    state_home: Path,
    model: str | None,
    effort: str | None,
    permission_mode: str,
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
    )
    runtime_provider = _custom_runtime(runtime)
    if runtime_provider is not None:
        env.update(runtime_provider.claude_env)
    argv = [executable]
    if model:
        argv.extend(["--model", model])
    if effort:
        argv.extend(["--effort", effort])
    argv.extend(["--permission-mode", permission_mode])
    return argv


def _codex_spec(
    executable: str,
    runtime: RuntimeProvider,
    env: dict[str, str],
    state_home: Path,
    model: str | None,
    effort: str | None,
    user_home: Path | None = None,
    session_model_provider: str | None = None,
    project_directory: Path | None = None,
) -> list[str]:
    _clear(env, "CODEX_HOME", "CODEX_SQLITE_HOME")
    env["CODEX_HOME"] = str(state_home)
    argv = [executable]
    runtime_provider = _custom_runtime(runtime)
    if runtime_provider is not None:
        profile = ensure_managed_config(
            runtime_provider,
            state_home,
            model,
            effort,
            user_home=user_home,
            session_model_provider=session_model_provider,
            project_directory=project_directory,
        )
        env[profile.env_key] = _required(runtime_provider.api_key, "Codex API key")
        argv.extend(["--profile", profile.name])
        # The profile contains the provider model, reasoning effort, and permission policy.
        return argv
    if user_home is not None:
        sync_codex_user_config(state_home, user_home, project_directory)
    if model:
        argv.extend(["--model", model])
    argv.extend(["--ask-for-approval", "never"])
    return argv


def _grok_spec(
    executable: str,
    runtime: RuntimeProvider,
    env: dict[str, str],
    state_home: Path,
    model: str | None,
    effort: str | None,
    sandbox_mode: str,
    always_approve: bool,
) -> list[str]:
    _clear(env, "GROK_HOME", "GROK_MODELS_BASE_URL", "GROK_MODELS_LIST_URL")
    env["GROK_HOME"] = str(state_home)
    argv = [executable]
    runtime_provider = _custom_runtime(runtime)
    if runtime_provider is not None:
        profile = ensure_managed_config(runtime_provider, state_home, model, effort)
        env[profile.env_key] = _required(runtime_provider.api_key, "Grok API key")
        argv.extend(["--model", profile.name])
    elif model:
        argv.extend(["--model", model])
    if effort:
        argv.extend(["--reasoning-effort", effort])
    argv.extend(["--sandbox", sandbox_mode])
    if always_approve:
        argv.append("--always-approve")
    return argv


def _custom_runtime(runtime: RuntimeProvider) -> RuntimeProvider | None:
    if runtime.endpoint is None:
        return None
    return runtime


def _runtime_with_permission_defaults(
    runtime: RuntimeProvider,
    settings: AppSettings,
) -> RuntimeProvider:
    """Use app settings only for permission values absent from a provider record."""
    if runtime.provider.app is AppKind.CLAUDE:
        return replace(
            runtime,
            permission_mode=runtime.permission_mode or settings.claude.permission_mode,
        )
    if runtime.provider.app is AppKind.CODEX:
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
