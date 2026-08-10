from __future__ import annotations

import pytest
import tomlkit

from ccs_plus.adapters import build_provider, runtime_from_provider
from ccs_plus.domain import AppKind, NewProvider, ProviderError
from ccs_plus.managed_config import ensure_managed_config


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
        )
    )
    return runtime_from_provider(provider)


def test_codex_profile_has_permissions_but_no_api_key(tmp_path) -> None:
    runtime = _runtime(AppKind.CODEX)
    profile = ensure_managed_config(runtime, tmp_path, None, None)
    path = tmp_path / f"{profile.name}.config.toml"
    content = path.read_text(encoding="utf-8")
    document = tomlkit.parse(content)

    assert "managed-secret-key" not in content
    assert document["approval_policy"] == "never"
    assert document["default_permissions"] == "ccs_plus_workspace_net"
    permission = document["permissions"]["ccs_plus_workspace_net"]
    assert permission["extends"] == ":workspace"
    assert permission["network"]["enabled"] is True
    assert permission["network"]["domains"]["*"] == "allow"
    assert document["windows"]["sandbox"] == "elevated"
    # Permission profiles and legacy sandbox settings do not compose.
    assert "sandbox_mode" not in document
    assert "sandbox_workspace_write" not in document
    assert document["model_providers"][profile.name]["env_key"] == profile.env_key


def test_codex_profile_preserves_windows_sandbox_and_project_trust(tmp_path) -> None:
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

    assert document["windows"]["sandbox"] == "unelevated"
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
