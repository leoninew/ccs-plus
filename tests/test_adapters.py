from __future__ import annotations

import pytest
import tomlkit

from ccs_plus.adapters import build_provider, display_configuration, runtime_from_provider
from ccs_plus.domain import (
    AppKind,
    ClaudeRuntime,
    CodexAppConfig,
    CodexRuntime,
    GrokRuntime,
    NewProvider,
    OpenCodeRuntime,
    Provider,
    ProviderError,
)

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _new_value(app: AppKind, effort: str | None = None) -> NewProvider:
    return NewProvider(
        app=app,
        name="Example Provider",
        endpoint="https://api.example.test/v1",
        api_key="test-secret-key",
        model="example-model",
        effort=effort,
        notes=None,
    )


def test_build_claude_provider_keeps_effort_in_cc_switch_shape() -> None:
    provider = build_provider(_new_value(AppKind.CLAUDE, "high"), _CODEX)
    assert provider.settings_config["effortLevel"] == "high"
    assert provider.settings_config["env"]["ANTHROPIC_AUTH_TOKEN"] == "test-secret-key"
    assert runtime_from_provider(provider).effort == "high"


@pytest.mark.parametrize(
    ("app", "runtime_type"),
    [
        (AppKind.CLAUDE, ClaudeRuntime),
        (AppKind.CODEX, CodexRuntime),
        (AppKind.GROK, GrokRuntime),
        (AppKind.OPENCODE, OpenCodeRuntime),
    ],
)
def test_runtime_uses_an_app_specific_type(app: AppKind, runtime_type: type[object]) -> None:
    value = _new_value(app)
    if app is AppKind.OPENCODE:
        value = NewProvider(
            app=app,
            name="Example Provider",
            endpoint="https://api.example.test/v1",
            api_key="test-secret-key",
            model="custom/example-model",
            effort=None,
            notes=None,
        )
    runtime = runtime_from_provider(build_provider(value, _CODEX))

    assert isinstance(runtime, runtime_type)


def test_build_codex_provider_uses_responses_api_and_app_defaults() -> None:
    provider = build_provider(_new_value(AppKind.CODEX, "xhigh"), _CODEX)
    document = tomlkit.parse(provider.settings_config["config"])
    assert document["model_provider"] == "custom"
    assert document["model_providers"]["custom"]["wire_api"] == "responses"
    assert document["approval_policy"] == "never"
    assert document["sandbox_mode"] == "danger-full-access"
    assert "sandbox_workspace_write" not in document
    runtime = runtime_from_provider(provider)
    assert runtime.endpoint == "https://api.example.test/v1"
    assert runtime.api_key == "test-secret-key"
    assert runtime.effort == "xhigh"
    assert runtime.approval_policy == "never"
    assert runtime.sandbox_mode == "danger-full-access"


def test_build_codex_provider_honors_configured_sandbox_mode() -> None:
    codex = CodexAppConfig(approval_policy="on-request", sandbox_mode="workspace-write")
    provider = build_provider(_new_value(AppKind.CODEX), codex)
    document = tomlkit.parse(provider.settings_config["config"])
    assert document["approval_policy"] == "on-request"
    assert document["sandbox_mode"] == "workspace-write"
    assert document["sandbox_workspace_write"]["network_access"] is True


def test_build_grok_provider_uses_cc_switch_required_fields() -> None:
    provider = build_provider(_new_value(AppKind.GROK, "xhigh"), _CODEX)
    document = tomlkit.parse(provider.settings_config["config"])
    model = document["model"]["example-model"]
    assert document["models"]["default"] == "example-model"
    assert document["models"]["default_reasoning_effort"] == "xhigh"
    assert model["api_backend"] == "responses"
    assert model["context_window"] == 500_000
    runtime = runtime_from_provider(provider)
    assert runtime.api_key == "test-secret-key"
    assert runtime.effort == "xhigh"


def test_runtime_uses_only_declared_env_key(monkeypatch) -> None:
    monkeypatch.setenv("DECLARED_PROVIDER_KEY", "from-environment")
    provider = Provider(
        id="existing",
        app=AppKind.CODEX,
        name="Existing",
        settings_config={
            "auth": {},
            "config": """
model_provider = "custom"
model = "example-model"
approval_policy = "never"
sandbox_mode = "danger-full-access"
[model_providers.custom]
base_url = "https://api.example.test/v1"
wire_api = "responses"
env_key = "DECLARED_PROVIDER_KEY"
""",
        },
        endpoints=("https://api.example.test/v1",),
        category="custom",
        created_at=None,
        notes=None,
        is_current=False,
    )
    runtime = runtime_from_provider(provider)
    assert runtime.api_key == "from-environment"
    assert runtime.approval_policy == "never"
    assert runtime.sandbox_mode == "danger-full-access"


def test_runtime_rejects_non_responses_codex_provider() -> None:
    provider = build_provider(_new_value(AppKind.CODEX), _CODEX)
    provider = Provider(
        **{
            **provider.__dict__,
            "settings_config": {
                "auth": {"OPENAI_API_KEY": "test-secret-key"},
                "config": """
model_provider = "custom"
[model_providers.custom]
base_url = "https://api.example.test/v1"
wire_api = "chat"
""",
            },
        }
    )
    with pytest.raises(ProviderError, match="Responses API"):
        runtime_from_provider(provider)


def test_opencode_runtime_parses_cc_switch_native_provider_shape() -> None:
    provider = Provider(
        id="nunu-grok",
        app=AppKind.OPENCODE,
        name="NuNu-grok",
        settings_config={
            "npm": "@ai-sdk/openai-compatible",
            "options": {
                "baseURL": "https://api.example.test/v1",
                "apiKey": "secret-key",
                "setCacheKey": True,
            },
            "models": {"grok-4.5": {"name": "grok-4.5"}},
        },
        endpoints=(),
        category=None,
        created_at=None,
        notes=None,
        is_current=False,
    )

    runtime = runtime_from_provider(provider)

    assert isinstance(runtime, OpenCodeRuntime)
    assert runtime.endpoint == "https://api.example.test/v1"
    assert runtime.api_key == "secret-key"
    assert runtime.model == "nunu-grok/grok-4.5"
    display = display_configuration(provider)
    assert display.endpoint == "https://api.example.test/v1"
    assert display.model == "nunu-grok/grok-4.5"


@pytest.mark.parametrize("app", list(AppKind))
def test_display_configuration_uses_the_active_settings_config_route(app: AppKind) -> None:
    value = _new_value(app)
    if app is AppKind.OPENCODE:
        value = NewProvider(
            app=app,
            name="Example Provider",
            endpoint="https://api.example.test/v1",
            api_key="test-secret-key",
            model="custom/example-model",
            effort=None,
            notes=None,
        )
    provider = build_provider(value, _CODEX)
    provider = Provider(**{**provider.__dict__, "endpoints": ("https://stale.example.test/v1",)})

    display = display_configuration(provider)

    assert display.endpoint == "https://api.example.test/v1"
    assert display.model in {"example-model", "custom/example-model"}
    assert display.effort is None


def test_display_configuration_uses_codex_top_level_base_url_as_fallback() -> None:
    provider = Provider(
        id="codex-top-level",
        app=AppKind.CODEX,
        name="Codex top-level",
        settings_config={
            "config": 'model = "example-model"\nbase_url = "https://top.example.test/v1"\n'
        },
        endpoints=(),
        category="custom",
        created_at=None,
        notes=None,
        is_current=False,
    )

    display = display_configuration(provider)

    assert display.endpoint == "https://top.example.test/v1"
    assert display.model == "example-model"
