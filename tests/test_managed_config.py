from __future__ import annotations

import pytest
import tomlkit

from ccs_plus.adapters import build_provider, runtime_from_provider
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, ProviderError
from ccs_plus.managed_config import ensure_managed_config

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


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
    assert document["model_providers"][profile.name]["env_key"] == profile.env_key


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
    assert document["default_permissions"] == ":workspace-write"


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


def test_codex_profile_removes_sandbox_config_and_preserves_project_trust(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    path = tmp_path / f"{profile.name}.config.toml"
    path.write_text(
        f"""# ccs-plus-managed: codex:{runtime.provider.id}
[windows]
sandbox = "unelevated"

[projects.'d:\\workspace']
trust_level = "trusted"
""",
        encoding="utf-8",
    )

    ensure_managed_config(runtime, tmp_path, None, None)
    document = tomlkit.parse(path.read_text(encoding="utf-8"))

    assert "windows" not in document
    assert document["projects"][r"d:\workspace"]["trust_level"] == "trusted"


def test_codex_profile_rejects_unmanaged_file(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    path = tmp_path / f"{profile.name}.config.toml"
    path.write_text('model = "user-owned"\n', encoding="utf-8")

    with pytest.raises(ProviderError, match="unmanaged"):
        ensure_managed_config(runtime, tmp_path, None, None)


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

    profile = ensure_managed_config(runtime, tmp_path, None, None)
    content = config_path.read_text(encoding="utf-8")
    document = tomlkit.parse(content)

    assert "managed-secret-key" not in content
    assert document["models"]["default"] == "user-model"
    assert document["model"][profile.name]["model"] == "example-model"
    assert document["model"][profile.name]["context_window"] == 500_000
    assert (tmp_path / "config.toml.ccs-plus.bak").is_file()
