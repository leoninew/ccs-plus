from __future__ import annotations

import pytest
import tomlkit

from ccs_plus.adapters import build_provider, runtime_from_provider
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, ProviderError
from ccs_plus.managed_config import ensure_managed_config as _ensure_managed_config
from ccs_plus.managed_config import remove_managed_config

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def ensure_managed_config(*args, **kwargs):
    kwargs.pop("user_home", None)
    kwargs.pop("project_directory", None)
    return _ensure_managed_config(
        *args,
        session_model_provider="ccs-plus-managed",
        **kwargs,
    )


def _runtime(app: AppKind):
    provider = build_provider(
        NewProvider(
            app=app,
            name="Example Provider",
            endpoint="https://api.example.test/v1",
            api_key="managed-secret-key",
            model="example-model",
            effort="high" if app is AppKind.CODEX else None,
            notes=None,
        ),
        _CODEX,
    )
    return runtime_from_provider(provider)


def test_codex_profile_uses_provider_policy_but_no_api_key(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    path = tmp_path / f"{profile.name}.config.toml"
    content = path.read_text(encoding="utf-8")
    document = tomlkit.parse(content)

    assert "managed-secret-key" not in content
    assert document["approval_policy"] == "never"
    assert document["default_permissions"] == ":danger-full-access"
    assert "permissions" not in document
    assert "windows" not in document
    # Permission profiles and legacy sandbox settings do not compose.
    assert "sandbox_mode" not in document
    assert "sandbox_workspace_write" not in document
    assert document["model_provider"] == "ccs-plus-managed"
    assert document["model_providers"]["ccs-plus-managed"]["env_key"] == profile.env_key


def test_codex_profile_follows_provider_sandbox_mode(tmp_path) -> None:
    provider = build_provider(
        NewProvider(
            app=AppKind.CODEX,
            name="Workspace Provider",
            endpoint="https://api.example.test/v1",
            api_key="managed-secret-key",
            model="example-model",
            effort=None,
            notes=None,
        ),
        CodexAppConfig(approval_policy="on-request", sandbox_mode="workspace-write"),
    )
    runtime = runtime_from_provider(provider)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    document = tomlkit.parse((tmp_path / f"{profile.name}.config.toml").read_text(encoding="utf-8"))
    assert document["approval_policy"] == "on-request"
    assert document["default_permissions"] == ":workspace"


def test_codex_profile_rejects_missing_provider_policy(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    runtime = type(runtime)(
        **{
            **runtime.__dict__,
            "approval_policy": None,
            "sandbox_mode": None,
        }
    )
    with pytest.raises(ProviderError, match="approval_policy"):
        ensure_managed_config(runtime, tmp_path, None, None)


def test_codex_profile_falls_back_to_settings_policy(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    runtime = type(runtime)(
        **{
            **runtime.__dict__,
            "approval_policy": None,
            "sandbox_mode": None,
        }
    )

    profile = ensure_managed_config(
        runtime,
        tmp_path,
        None,
        None,
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )
    document = tomlkit.parse((tmp_path / f"{profile.name}.config.toml").read_text(encoding="utf-8"))

    assert document["approval_policy"] == "on-request"
    assert document["default_permissions"] == ":workspace"


def test_codex_profile_removes_legacy_extension_and_project_settings(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    path = tmp_path / f"{profile.name}.config.toml"
    path.write_text(
        f"""# ccs-plus-managed: codex:{runtime.provider.id}
[windows]
sandbox = "unelevated"

[projects.'d:\\workspace']
trust_level = "trusted"

[mcp_servers.legacy]
command = "legacy"

[plugins."legacy@local"]
enabled = true

[marketplaces.legacy]
source = "local"

[shell_environment_policy]
inherit = "all"
""",
        encoding="utf-8",
    )

    ensure_managed_config(runtime, tmp_path, None, None)
    document = tomlkit.parse(path.read_text(encoding="utf-8"))

    assert "windows" not in document
    assert "projects" not in document
    assert "mcp_servers" not in document
    assert "plugins" not in document
    assert "marketplaces" not in document
    assert "shell_environment_policy" not in document


def test_codex_profile_rejects_unmanaged_file(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    path = tmp_path / f"{profile.name}.config.toml"
    path.write_text('model = "user-owned"\n', encoding="utf-8")

    with pytest.raises(ProviderError, match="unmanaged"):
        ensure_managed_config(runtime, tmp_path, None, None)


def test_remove_managed_codex_profile_requires_matching_marker(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    path = tmp_path / f"{profile.name}.config.toml"

    assert remove_managed_config(tmp_path, runtime.provider.id) is True
    assert not path.exists()

    path.write_text('model = "user-owned"\n', encoding="utf-8")
    assert remove_managed_config(tmp_path, runtime.provider.id) is False
    assert path.exists()


def test_codex_profiles_share_model_provider_across_providers(tmp_path) -> None:
    first = _runtime(AppKind.CODEX)
    second_provider = build_provider(
        NewProvider(
            app=AppKind.CODEX,
            name="Second Provider",
            endpoint="https://second.example.test/v1",
            api_key="second-secret-key",
            model="second-model",
            effort="minimal",
            notes=None,
        ),
        _CODEX,
    )
    second = runtime_from_provider(second_provider)

    first_profile = ensure_managed_config(first, tmp_path, None, None)
    second_profile = ensure_managed_config(second, tmp_path, None, None)
    first_document = tomlkit.parse(
        (tmp_path / f"{first_profile.name}.config.toml").read_text(encoding="utf-8")
    )
    second_document = tomlkit.parse(
        (tmp_path / f"{second_profile.name}.config.toml").read_text(encoding="utf-8")
    )

    assert first_profile.name != second_profile.name
    assert first_document["model_provider"] == "ccs-plus-managed"
    assert second_document["model_provider"] == "ccs-plus-managed"
    assert list(first_document["model_providers"]) == ["ccs-plus-managed"]
    assert list(second_document["model_providers"]) == ["ccs-plus-managed"]


def test_codex_profile_requires_configured_session_model_provider(tmp_path) -> None:
    with pytest.raises(ProviderError, match="session_model_provider"):
        _ensure_managed_config(_runtime(AppKind.CODEX), tmp_path, None, None)


def test_grok_config_preserves_default_and_uses_managed_model(tmp_path) -> None:
    runtime = _runtime(AppKind.GROK)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """# user configuration
[models]
default = "user-model"

[model.user-model]
model = "user-model"
base_url = "https://user.example.test/v1"
name = "User"
env_key = "USER_KEY"
api_backend = "responses"
context_window = 500000
""",
        encoding="utf-8",
    )

    profile = ensure_managed_config(runtime, tmp_path, None, "xhigh")
    content = config_path.read_text(encoding="utf-8")
    document = tomlkit.parse(content)

    assert "managed-secret-key" not in content
    assert f"ccs-plus-managed: grok:{runtime.provider.id}" in content
    assert document["models"]["default"] == "user-model"
    assert document["models"]["default_reasoning_effort"] == "xhigh"
    assert document["model"][profile.name]["model"] == "example-model"
    assert document["model"][profile.name]["context_window"] == 500_000
    assert not (tmp_path / "config.toml.ccs-plus.bak").exists()


def test_grok_config_keeps_only_current_managed_model(tmp_path) -> None:
    first = _runtime(AppKind.GROK)
    second_provider = build_provider(
        NewProvider(
            app=AppKind.GROK,
            name="Second Grok Provider",
            endpoint="https://second.example.test/v1",
            api_key="second-managed-secret-key",
            model="second-model",
            effort=None,
            notes=None,
        ),
        _CODEX,
    )
    second = runtime_from_provider(second_provider)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """[models]
default = "user-model"

[model.user-model]
model = "user-model"
base_url = "https://user.example.test/v1"
name = "User model"
env_key = "USER_KEY"
api_backend = "responses"
context_window = 500000
""",
        encoding="utf-8",
    )

    first_profile = ensure_managed_config(first, tmp_path, None, None)
    document = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    document["models"]["default"] = first_profile.name
    config_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    second_profile = ensure_managed_config(second, tmp_path, None, None)
    document = tomlkit.parse(config_path.read_text(encoding="utf-8"))

    assert set(document["model"]) == {"user-model", second_profile.name}
    assert first_profile.name not in document["model"]
    assert document["models"].get("default") is None


def test_grok_config_rejects_unmanaged_profile(tmp_path) -> None:
    runtime = _runtime(AppKind.GROK)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    (tmp_path / "config.toml").write_text(
        f"""
[model.{profile.name}]
model = "user-owned"
base_url = "https://user.example.test/v1"
name = "User"
env_key = "USER_KEY"
api_backend = "responses"
context_window = 500000
""",
        encoding="utf-8",
    )

    with pytest.raises(ProviderError, match="unmanaged Grok"):
        ensure_managed_config(runtime, tmp_path, None, None)


def test_grok_config_rewrites_profile_after_cli_strips_marker(tmp_path) -> None:
    runtime = _runtime(AppKind.GROK)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    (tmp_path / "config.toml").write_text(
        f"""
[models]
default = "user-model"

[model.{profile.name}]
model = "stale-model"
base_url = "https://stale.example.test/v1"
name = "Stale"
env_key = "{profile.env_key}"
api_backend = "responses"
context_window = 500000
""",
        encoding="utf-8",
    )

    ensure_managed_config(runtime, tmp_path, "fresh-model", None)
    content = (tmp_path / "config.toml").read_text(encoding="utf-8")
    document = tomlkit.parse(content)

    assert f"ccs-plus-managed: grok:{runtime.provider.id}" in content
    assert document["models"]["default"] == "user-model"
    assert document["model"][profile.name]["model"] == "fresh-model"
    assert document["model"][profile.name]["base_url"] == "https://api.example.test/v1"
    assert document["model"][profile.name]["env_key"] == profile.env_key
