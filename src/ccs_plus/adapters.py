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
    CodexAppConfig,
    NewProvider,
    Provider,
    ProviderDisplay,
    ProviderError,
    RuntimeProvider,
)


def build_provider(value: NewProvider, codex: CodexAppConfig) -> Provider:
    created_at = int(time.time() * 1000)
    provider_id = f"ccs-plus-{uuid.uuid4().hex}"
    if value.app is AppKind.CLAUDE:
        settings = _new_claude_settings(value)
    elif value.app is AppKind.CODEX:
        settings = _new_codex_settings(value, codex)
    else:
        settings = _new_grok_settings(value)
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


def runtime_from_provider(provider: Provider) -> RuntimeProvider:
    if provider.is_official:
        return RuntimeProvider(
            provider=provider,
            endpoint=None,
            api_key=None,
            model=None,
            effort=None,
        )
    if provider.app is AppKind.CLAUDE:
        return _claude_runtime(provider)
    if provider.app is AppKind.CODEX:
        return _codex_runtime(provider)
    return _grok_runtime(provider)


def display_configuration(provider: Provider) -> ProviderDisplay:
    if provider.is_official:
        return ProviderDisplay(endpoint=None, model=None, effort=None)
    try:
        if provider.app is AppKind.CLAUDE:
            return _display_claude_configuration(provider)
        if provider.app is AppKind.CODEX:
            return _display_codex_configuration(provider)
        return _display_grok_configuration(provider)
    except ProviderError:
        return ProviderDisplay(endpoint=None, model=None, effort=None)


def _new_claude_settings(value: NewProvider) -> dict[str, Any]:
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


def _new_codex_settings(value: NewProvider, codex: CodexAppConfig) -> dict[str, Any]:
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


def _new_grok_settings(value: NewProvider) -> dict[str, Any]:
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


def _claude_runtime(provider: Provider) -> RuntimeProvider:
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
    return RuntimeProvider(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        effort=_as_string(provider.settings_config.get("effortLevel")),
        claude_env=values,
    )


def _display_claude_configuration(provider: Provider) -> ProviderDisplay:
    env = _mapping(provider.settings_config.get("env"), "Claude env")
    return ProviderDisplay(
        endpoint=_as_string(env.get("ANTHROPIC_BASE_URL")),
        model=_as_string(env.get("ANTHROPIC_MODEL"))
        or _as_string(env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")),
        effort=_as_string(provider.settings_config.get("effortLevel")),
    )


def _codex_runtime(provider: Provider) -> RuntimeProvider:
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
    return RuntimeProvider(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=_as_string(_value(document.get("model"))),
        effort=_as_string(_value(document.get("model_reasoning_effort"))),
        approval_policy=_as_string(_value(document.get("approval_policy"))),
        sandbox_mode=_as_string(_value(document.get("sandbox_mode"))),
    )


def _display_codex_configuration(provider: Provider) -> ProviderDisplay:
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


def _grok_runtime(provider: Provider) -> RuntimeProvider:
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
    return RuntimeProvider(
        provider=provider,
        endpoint=endpoint,
        api_key=api_key,
        model=_as_string(_value(model_config.get("model"))) or model_name,
        effort=_as_string(_value(models.get("default_reasoning_effort"))),
    )


def _display_grok_configuration(provider: Provider) -> ProviderDisplay:
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


def _require(value: str | None, label: str) -> str:
    if not value:
        raise ProviderError(f"{label} is missing from cc-switch settings_config.")
    return value
