from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from os import environ
from typing import Any

import tomlkit
from tomlkit import TOMLDocument

from ccs_plus.domain import (
    AppKind,
    ClaudeRuntime,
    CodexAppConfig,
    CodexRuntime,
    GrokRuntime,
    NewProvider,
    OpenCodeRuntime,
    Provider,
    ProviderDisplay,
    ProviderError,
    RuntimeConfig,
)


class ProviderAdapter:
    def new_settings(self, value: NewProvider, codex: CodexAppConfig) -> dict[str, Any]:
        raise NotImplementedError

    def runtime(self, provider: Provider) -> RuntimeConfig:
        raise NotImplementedError

    def display(self, provider: Provider) -> ProviderDisplay:
        raise NotImplementedError


class ClaudeProviderAdapter(ProviderAdapter):
    def new_settings(self, value: NewProvider, codex: CodexAppConfig) -> dict[str, Any]:
        return _environment_settings(value)

    def runtime(self, provider: Provider) -> RuntimeConfig:
        if provider.is_official:
            return ClaudeRuntime(provider, None, None, None, None)
        return _environment_runtime(provider)

    def display(self, provider: Provider) -> ProviderDisplay:
        return _environment_display(provider)


class CodexProviderAdapter(ProviderAdapter):
    def new_settings(self, value: NewProvider, codex: CodexAppConfig) -> dict[str, Any]:
        return _profile_settings(value, codex)

    def runtime(self, provider: Provider) -> RuntimeConfig:
        if provider.is_official:
            return CodexRuntime(provider, None, None, None, None)
        return _profile_runtime(provider)

    def display(self, provider: Provider) -> ProviderDisplay:
        return _profile_display(provider)


class GrokProviderAdapter(ProviderAdapter):
    def new_settings(self, value: NewProvider, codex: CodexAppConfig) -> dict[str, Any]:
        return _registry_settings(value)

    def runtime(self, provider: Provider) -> RuntimeConfig:
        if provider.is_official:
            return GrokRuntime(provider, None, None, None, None)
        return _registry_runtime(provider)

    def display(self, provider: Provider) -> ProviderDisplay:
        return _registry_display(provider)


class OpenCodeProviderAdapter(ProviderAdapter):
    def new_settings(self, value: NewProvider, codex: CodexAppConfig) -> dict[str, Any]:
        return _opencode_settings(value)

    def runtime(self, provider: Provider) -> RuntimeConfig:
        if provider.is_official:
            return OpenCodeRuntime(provider, None, None, None, None)
        return _opencode_runtime(provider)

    def display(self, provider: Provider) -> ProviderDisplay:
        return _opencode_display(provider)


def provider_adapter_for(app: AppKind) -> ProviderAdapter:
    adapters: dict[AppKind, ProviderAdapter] = {
        AppKind.CLAUDE: ClaudeProviderAdapter(),
        AppKind.CODEX: CodexProviderAdapter(),
        AppKind.GROK: GrokProviderAdapter(),
        AppKind.OPENCODE: OpenCodeProviderAdapter(),
    }
    return adapters[app]


def build_provider(value: NewProvider, codex: CodexAppConfig) -> Provider:
    created_at = int(time.time() * 1000)
    provider_id = f"ccs-plus-{uuid.uuid4().hex}"
    settings = provider_adapter_for(value.app).new_settings(value, codex)
    return Provider(
        id=provider_id,
        app=value.app,
        name=value.name.strip(),
        settings_config=settings,
        endpoints=(value.endpoint.strip(),),
        category="custom",
        created_at=created_at,
        notes=value.notes.strip() if value.notes else None,
        is_current=False,
        meta={"ccsPlusManaged": True},
    )


def runtime_from_provider(provider: Provider) -> RuntimeConfig:
    return provider_adapter_for(provider.app).runtime(provider)


def display_configuration(provider: Provider) -> ProviderDisplay:
    if provider.is_official:
        return ProviderDisplay(endpoint=None, model=None, effort=None)
    try:
        return provider_adapter_for(provider.app).display(provider)
    except ProviderError:
        return ProviderDisplay(endpoint=None, model=None, effort=None)


def _environment_settings(value: NewProvider) -> dict[str, Any]:
    model = value.model.strip()
    settings: dict[str, Any] = {
        "env": {
            "ANTHROPIC_BASE_URL": value.endpoint.strip(),
            "ANTHROPIC_AUTH_TOKEN": value.api_key,
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        }
    }
    if value.effort:
        settings["effortLevel"] = value.effort.strip()
    return settings


def _profile_settings(value: NewProvider, codex: CodexAppConfig) -> dict[str, Any]:
    document = tomlkit.document()
    document["model_provider"] = "custom"
    document["model"] = value.model.strip()
    if value.effort:
        document["model_reasoning_effort"] = value.effort
    document["approval_policy"] = codex.approval_policy
    document["sandbox_mode"] = codex.sandbox_mode
    providers = tomlkit.table()
    custom = tomlkit.table()
    custom["name"] = value.name.strip()
    custom["base_url"] = value.endpoint.strip()
    custom["wire_api"] = "responses"
    providers["custom"] = custom
    document["model_providers"] = providers
    if codex.sandbox_mode == "workspace-write":
        workspace = tomlkit.table()
        workspace["network_access"] = True
        document["sandbox_workspace_write"] = workspace
    return {
        "auth": {"OPENAI_API_KEY": value.api_key},
        "config": tomlkit.dumps(document),
    }


def _registry_settings(value: NewProvider) -> dict[str, Any]:
    document = tomlkit.document()
    models = tomlkit.table()
    models["default"] = value.model.strip()
    if value.effort:
        models["default_reasoning_effort"] = value.effort.strip()
    document["models"] = models
    model_configs = tomlkit.table()
    model = tomlkit.table()
    model["model"] = value.model.strip()
    model["base_url"] = value.endpoint.strip()
    model["name"] = value.name.strip()
    model["api_key"] = value.api_key
    model["api_backend"] = "responses"
    model["context_window"] = 500_000
    model_configs[value.model.strip()] = model
    document["model"] = model_configs
    return {"config": tomlkit.dumps(document)}


def _environment_runtime(provider: Provider) -> ClaudeRuntime:
    env = _mapping(provider.settings_config.get("env"), "Claude env")
    values: dict[str, str] = {}
    for key, value in env.items():
        normalized_value = _as_string(value)
        if normalized_value:
            values[key] = normalized_value
    endpoint = values.get("ANTHROPIC_BASE_URL")
    api_key = values.get("ANTHROPIC_AUTH_TOKEN") or values.get("ANTHROPIC_API_KEY")
    model = values.get("ANTHROPIC_MODEL") or values.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
    _require(endpoint, "Claude ANTHROPIC_BASE_URL")
    _require(api_key, "Claude API key")
    return ClaudeRuntime(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        effort=_as_string(provider.settings_config.get("effortLevel")),
        claude_env=values,
        permission_mode=_as_string(provider.settings_config.get("permission_mode")),
    )


def _environment_display(provider: Provider) -> ProviderDisplay:
    env = _mapping(provider.settings_config.get("env"), "Claude env")
    return ProviderDisplay(
        endpoint=_as_string(env.get("ANTHROPIC_BASE_URL")),
        model=_as_string(env.get("ANTHROPIC_MODEL"))
        or _as_string(env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")),
        effort=_as_string(provider.settings_config.get("effortLevel")),
    )


def _profile_runtime(provider: Provider) -> CodexRuntime:
    document = _parse_toml(provider, "Codex")
    provider_id = _as_string(_value(document.get("model_provider")))
    providers = document.get("model_providers")
    provider_config = _value(providers.get(provider_id)) if providers and provider_id else None
    provider_values = _mapping(provider_config, "Codex model provider")
    endpoint = _as_string(_value(provider_values.get("base_url")))
    auth = _mapping(provider.settings_config.get("auth"), "Codex auth", required=False)
    api_key = _as_string(auth.get("OPENAI_API_KEY")) or _as_string(
        _value(provider_values.get("experimental_bearer_token"))
    )
    if not api_key:
        env_key = _as_string(_value(provider_values.get("env_key")))
        api_key = _as_string(environ.get(env_key)) if env_key else None
    wire_api = _as_string(_value(provider_values.get("wire_api")))
    if wire_api and wire_api != "responses":
        raise ProviderError(f"Codex provider {provider.id} does not use Responses API.")
    _require(endpoint, "Codex provider base_url")
    _require(api_key, "Codex API key")
    return CodexRuntime(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=_as_string(_value(document.get("model"))),
        effort=_as_string(_value(document.get("model_reasoning_effort"))),
        approval_policy=_as_string(_value(document.get("approval_policy"))),
        sandbox_mode=_as_string(_value(document.get("sandbox_mode"))),
    )


def _profile_display(provider: Provider) -> ProviderDisplay:
    document = _parse_toml(provider, "Codex")
    provider_id = _as_string(_value(document.get("model_provider")))
    providers = document.get("model_providers")
    endpoint = None
    if isinstance(providers, Mapping) and provider_id:
        active_provider = _value(providers.get(provider_id))
        if isinstance(active_provider, Mapping):
            endpoint = _as_string(_value(active_provider.get("base_url")))
    return ProviderDisplay(
        endpoint=endpoint or _as_string(_value(document.get("base_url"))),
        model=_as_string(_value(document.get("model"))),
        effort=_as_string(_value(document.get("model_reasoning_effort"))),
    )


def _registry_runtime(provider: Provider) -> GrokRuntime:
    config_text = _as_string(provider.settings_config.get("config"))
    if not config_text:
        raise ProviderError(f"Grok provider {provider.id} has no settings_config.config.")
    try:
        document = tomlkit.parse(config_text)
    except Exception as exc:
        raise ProviderError(f"Grok provider {provider.id} has invalid TOML config: {exc}") from exc
    models = _mapping(_value(document.get("models")), "Grok models")
    model_name = _require(_as_string(_value(models.get("default"))), "Grok default model")
    model_configs = _mapping(_value(document.get("model")), "Grok model")
    model_config = _mapping(_value(model_configs.get(model_name)), "Grok default model")
    endpoint = _as_string(_value(model_config.get("base_url")))
    api_key = _as_string(_value(model_config.get("api_key")))
    if not api_key:
        env_key = _as_string(_value(model_config.get("env_key")))
        api_key = _as_string(environ.get(env_key)) if env_key else None
    backend = _as_string(_value(model_config.get("api_backend")))
    if backend and backend != "responses":
        raise ProviderError(f"Grok provider {provider.id} does not use Responses API.")
    _require(endpoint, "Grok provider base_url")
    _require(api_key, "Grok API key")
    return GrokRuntime(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=_as_string(_value(model_config.get("model"))) or model_name,
        effort=_as_string(_value(models.get("default_reasoning_effort"))),
        sandbox_mode=_as_string(_value(document.get("sandbox_mode"))),
        always_approve=_as_bool(_value(document.get("always_approve"))),
    )


def _registry_display(provider: Provider) -> ProviderDisplay:
    document = _parse_toml(provider, "Grok")
    models = _mapping(_value(document.get("models")), "Grok models")
    model_name = _require(_as_string(_value(models.get("default"))), "Grok default model")
    model_configs = _mapping(_value(document.get("model")), "Grok model")
    model_config = _mapping(_value(model_configs.get(model_name)), "Grok default model")
    return ProviderDisplay(
        endpoint=_as_string(_value(model_config.get("base_url"))),
        model=_as_string(_value(model_config.get("model"))) or model_name,
        effort=_as_string(_value(models.get("default_reasoning_effort"))),
    )


def _opencode_settings(value: NewProvider) -> dict[str, Any]:
    # Store in cc-switch-compatible OpenCode provider shape (npm + options + models).
    model = value.model.strip()
    provider_id = "custom"
    model_id = model
    if "/" in model:
        provider_id, model_id = model.split("/", 1)
        provider_id = provider_id.strip() or "custom"
        model_id = model_id.strip() or model
    return {
        "npm": "@ai-sdk/openai-compatible",
        "options": {
            "baseURL": value.endpoint.strip(),
            "apiKey": value.api_key,
        },
        "models": {model_id: {"name": model_id}},
        # ccs-plus extras (ignored by cc-switch UI, used by our runtime fallbacks)
        "model": f"{provider_id}/{model_id}",
        "provider_id": provider_id,
        "effort": value.effort.strip() if value.effort else None,
        "permission_mode": None,
        "always_approve": None,
    }


def _opencode_runtime(provider: Provider) -> OpenCodeRuntime:
    endpoint, api_key, model, effort, permission_mode, always_approve = _parse_opencode_config(
        provider
    )
    _require(endpoint, "OpenCode endpoint")
    _require(api_key, "OpenCode API key")
    _require(model, "OpenCode model")
    return OpenCodeRuntime(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        effort=effort,
        permission_mode=permission_mode,
        always_approve=always_approve,
    )


def _opencode_display(provider: Provider) -> ProviderDisplay:
    endpoint, _api_key, model, effort, _permission, _always = _parse_opencode_config(provider)
    return ProviderDisplay(endpoint=endpoint, model=model, effort=effort)


def _parse_opencode_config(
    provider: Provider,
) -> tuple[str | None, str | None, str | None, str | None, str | None, bool | None]:
    """Parse ccs-plus or cc-switch native OpenCode provider settings_config.

    cc-switch stores the OpenCode provider block itself::

        {"npm": "...", "options": {"baseURL", "apiKey"}, "models": {"id": {...}}}

    ccs-plus also accepts a flat shape with endpoint/api_key/model.
    """
    config = provider.settings_config
    options = config.get("options")
    options_map = options if isinstance(options, Mapping) else {}

    endpoint = (
        _as_string(config.get("endpoint"))
        or _as_string(options_map.get("baseURL"))
        or _as_string(options_map.get("baseUrl"))
    )
    api_key = (
        _as_string(config.get("api_key"))
        or _as_string(options_map.get("apiKey"))
        or _as_string(options_map.get("api_key"))
    )

    model = _as_string(config.get("model"))
    if not model:
        models = config.get("models")
        model_id: str | None = None
        if isinstance(models, Mapping) and models:
            first = next(iter(models.keys()))
            model_id = _as_string(first)
        provider_id = _as_string(config.get("provider_id")) or provider.id
        if model_id:
            model = f"{provider_id}/{model_id}"

    effort = _as_string(config.get("effort"))
    permission_mode = _as_string(config.get("permission_mode"))
    always_approve = _as_bool(config.get("always_approve"))
    return endpoint, api_key, model, effort, permission_mode, always_approve


def _parse_toml(provider: Provider, app_name: str) -> TOMLDocument:
    config_text = _as_string(provider.settings_config.get("config"))
    if not config_text:
        raise ProviderError(f"{app_name} provider {provider.id} has no settings_config.config.")
    try:
        return tomlkit.parse(config_text)
    except Exception as exc:
        raise ProviderError(
            f"{app_name} provider {provider.id} has invalid TOML config: {exc}"
        ) from exc


def _mapping(value: object, name: str, required: bool = True) -> Mapping[str, Any]:
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping):
        raise ProviderError(f"{name} is missing or invalid.")
    return value


def _value(value: object) -> object:
    return getattr(value, "value", value)


def _as_string(value: object) -> str | None:
    value = _value(value)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _as_bool(value: object) -> bool | None:
    value = _value(value)
    return value if isinstance(value, bool) else None


def _require(value: str | None, label: str) -> str:
    if not value:
        raise ProviderError(f"{label} is missing from cc-switch settings_config.")
    return value
