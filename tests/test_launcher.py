from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
import tomlkit
from conftest import make_app_settings

from ccs_plus.adapters import build_provider
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, Provider, ProviderError
from ccs_plus.home_visibility import _is_link, _links_to
from ccs_plus.launcher import LaunchSpec, build_launch_spec, launch
from ccs_plus.settings import AppSettings

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _settings(root: Path) -> AppSettings:
    return make_app_settings(root)


def _provider(
    app: AppKind,
    *,
    name: str = "Example Provider",
    endpoint: str = "https://api.example.test/v1",
    model: str = "example-model",
):
    return build_provider(
        NewProvider(
            app=app,
            name=name,
            endpoint=endpoint,
            api_key="launch-secret-key",
            model=model,
            effort="high" if app is not AppKind.GROK else "xhigh",
            notes=None,
        ),
        _CODEX,
    )


@pytest.mark.parametrize(
    ("app", "required_args"),
    [
        (AppKind.CLAUDE, ("--permission-mode", "bypassPermissions")),
        (AppKind.CODEX, ("--profile",)),
        (AppKind.GROK, ("--sandbox", "workspace", "--always-approve")),
    ],
)
def test_launch_specs_keep_secret_out_of_argv_and_use_expected_home(
    tmp_path, monkeypatch, app: AppKind, required_args: tuple[str, ...]
) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-cli")
    monkeypatch.setenv("CODEX_HOME", "temporary-codex-home")
    monkeypatch.setenv("CODEX_SQLITE_HOME", "temporary-sqlite-home")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "temporary-claude-home")
    monkeypatch.setenv("GROK_HOME", "temporary-grok-home")

    settings = _settings(tmp_path)
    provider = _provider(app)
    spec = build_launch_spec(provider, settings, tmp_path)

    assert "launch-secret-key" not in spec.argv
    assert all(argument in spec.argv for argument in required_args)
    state_home = settings.state_home(app.value)
    state_keys = {
        AppKind.CLAUDE: "CLAUDE_CONFIG_DIR",
        AppKind.CODEX: "CODEX_HOME",
        AppKind.GROK: "GROK_HOME",
    }
    state_key = state_keys[app]
    expected_home = state_home
    assert spec.env[state_key] == str(expected_home)
    assert spec.cwd == tmp_path.resolve()
    assert "--effort" not in spec.argv
    if app is AppKind.GROK:
        profile_name = spec.argv[spec.argv.index("--model") + 1]
        document = tomlkit.parse(
            (Path(spec.env["GROK_HOME"]) / "config.toml").read_text(encoding="utf-8")
        )
        assert "--reasoning-effort" not in spec.argv
        assert document["models"]["default_reasoning_effort"] == "xhigh"
        assert document["model"][profile_name]["model"] == "example-model"
    if app is AppKind.CLAUDE:
        assert "--model" not in spec.argv
        assert spec.env["ANTHROPIC_MODEL"] == "example-model"
        assert spec.env["CLAUDE_CODE_EFFORT_LEVEL"] == "high"
    if app is AppKind.CODEX:
        assert "--model" not in spec.argv
        assert "CODEX_SQLITE_HOME" not in spec.env
        assert "--sandbox" not in spec.argv
        assert "--dangerously-bypass-approvals-and-sandbox" not in spec.argv


def test_codex_launch_uses_provider_profile_for_approval_policy(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    provider = build_provider(
        NewProvider(
            app=AppKind.CODEX,
            name="On Request",
            endpoint="https://api.example.test/v1",
            api_key="launch-secret-key",
            model="example-model",
            effort=None,
            notes=None,
        ),
        CodexAppConfig(approval_policy="on-request", sandbox_mode="workspace-write"),
    )
    settings = _settings(tmp_path)
    spec = build_launch_spec(provider, settings, tmp_path)
    profile_name = spec.argv[spec.argv.index("--profile") + 1]
    profile_text = (Path(spec.env["CODEX_HOME"]) / f"{profile_name}.config.toml").read_text(
        encoding="utf-8"
    )
    assert 'approval_policy = "on-request"' in profile_text
    assert 'default_permissions = ":workspace"' in profile_text


def test_codex_launch_falls_back_to_settings_policy_without_provider_policy(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    provider = build_provider(
        NewProvider(
            app=AppKind.CODEX,
            name="No Policy Provider",
            endpoint="https://api.example.test/v1",
            api_key="launch-secret-key",
            model="example-model",
            effort=None,
            notes=None,
        ),
        _CODEX,
    )
    config = tomlkit.parse(provider.settings_config["config"])
    del config["approval_policy"]
    del config["sandbox_mode"]
    provider = replace(
        provider,
        settings_config={**provider.settings_config, "config": tomlkit.dumps(config)},
    )
    settings = make_app_settings(
        tmp_path,
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    spec = build_launch_spec(provider, settings, tmp_path)

    profile_name = spec.argv[spec.argv.index("--profile") + 1]
    profile_text = (Path(spec.env["CODEX_HOME"]) / f"{profile_name}.config.toml").read_text(
        encoding="utf-8"
    )
    assert 'approval_policy = "on-request"' in profile_text
    assert 'default_permissions = ":workspace"' in profile_text


def test_launch_uses_settings_permission_defaults_when_provider_omits_them(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-cli")
    settings = make_app_settings(
        tmp_path,
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        claude_permission_mode="manual",
        grok_sandbox_mode="restricted",
        grok_always_approve=False,
    )

    claude = _provider(AppKind.CLAUDE)
    codex = _provider(AppKind.CODEX)
    codex = Provider(
        **{
            **codex.__dict__,
            "settings_config": {
                **codex.settings_config,
                "config": codex.settings_config["config"]
                .replace('approval_policy = "never"\n', "")
                .replace('sandbox_mode = "danger-full-access"\n', ""),
            },
        }
    )
    grok = _provider(AppKind.GROK)

    claude_spec = build_launch_spec(claude, settings, tmp_path)
    codex_spec = build_launch_spec(codex, settings, tmp_path)
    grok_spec = build_launch_spec(grok, settings, tmp_path)

    assert claude_spec.argv[-2:] == ("--permission-mode", "manual")
    profile_name = codex_spec.argv[codex_spec.argv.index("--profile") + 1]
    profile_text = (Path(codex_spec.env["CODEX_HOME"]) / f"{profile_name}.config.toml").read_text(
        encoding="utf-8"
    )
    assert 'approval_policy = "on-request"' in profile_text
    assert 'default_permissions = ":workspace"' in profile_text
    assert grok_spec.argv[grok_spec.argv.index("--sandbox") + 1] == "restricted"
    assert "--always-approve" not in grok_spec.argv


def test_launch_keeps_provider_permission_settings_over_app_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-cli")
    settings = make_app_settings(
        tmp_path,
        claude_permission_mode="manual",
        grok_sandbox_mode="restricted",
        grok_always_approve=True,
    )
    claude = _provider(AppKind.CLAUDE)
    claude = Provider(
        **{
            **claude.__dict__,
            "settings_config": {**claude.settings_config, "permission_mode": "acceptEdits"},
        }
    )
    grok = _provider(AppKind.GROK)
    grok = Provider(
        **{
            **grok.__dict__,
            "settings_config": {
                **grok.settings_config,
                "config": grok.settings_config["config"].replace(
                    "[models]",
                    'sandbox_mode = "workspace"\nalways_approve = false\n\n[models]',
                ),
            },
        }
    )

    claude_spec = build_launch_spec(claude, settings, tmp_path)
    grok_spec = build_launch_spec(grok, settings, tmp_path)

    assert claude_spec.argv[-2:] == ("--permission-mode", "acceptEdits")
    assert grok_spec.argv[grok_spec.argv.index("--sandbox") + 1] == "workspace"
    assert "--always-approve" not in grok_spec.argv


def test_claude_launch_uses_configured_permission_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-claude")
    settings = make_app_settings(tmp_path, claude_permission_mode="manual")

    spec = build_launch_spec(_provider(AppKind.CLAUDE), settings, tmp_path)

    assert spec.argv[-2:] == ("--permission-mode", "manual")
    assert "--dangerously-skip-permissions" not in spec.argv


def test_grok_launch_uses_configured_permission_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-grok")
    settings = make_app_settings(
        tmp_path,
        grok_sandbox_mode="restricted",
        grok_always_approve=False,
    )

    spec = build_launch_spec(_provider(AppKind.GROK), settings, tmp_path)

    assert "--sandbox" in spec.argv
    assert spec.argv[spec.argv.index("--sandbox") + 1] == "restricted"
    assert "--always-approve" not in spec.argv


def test_codex_launch_profile_contains_no_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    spec = build_launch_spec(_provider(AppKind.CODEX), _settings(tmp_path), tmp_path)

    profile_name = spec.argv[spec.argv.index("--profile") + 1]
    profile = Path(spec.env["CODEX_HOME"]) / f"{profile_name}.config.toml"
    assert "launch-secret-key" not in profile.read_text(encoding="utf-8")
    assert any(key.startswith("CCS_PLUS_CODEX_") for key in spec.env)


def test_codex_launch_uses_configured_session_model_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    settings = make_app_settings(tmp_path, session_model_provider="ccs-plus-shared")

    spec = build_launch_spec(_provider(AppKind.CODEX), settings, tmp_path)

    profile_name = spec.argv[spec.argv.index("--profile") + 1]
    document = tomlkit.parse(
        (Path(spec.env["CODEX_HOME"]) / f"{profile_name}.config.toml").read_text(encoding="utf-8")
    )
    assert document["model_provider"] == "ccs-plus-shared"
    assert list(document["model_providers"]) == ["ccs-plus-shared"]


def test_launch_uses_current_directory_when_cwd_is_omitted(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-claude")
    monkeypatch.chdir(tmp_path)

    spec = build_launch_spec(_provider(AppKind.CLAUDE), _settings(tmp_path))

    assert spec.cwd == tmp_path.resolve()


@pytest.mark.parametrize(
    ("app", "effort"),
    [
        (AppKind.CLAUDE, "low"),
        (AppKind.CODEX, "minimal"),
        (AppKind.GROK, "high"),
    ],
)
def test_launch_overrides_provider_model_and_effort_without_native_override_args(
    tmp_path, monkeypatch, app: AppKind, effort: str
) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-cli")

    spec = build_launch_spec(
        _provider(app),
        _settings(tmp_path),
        tmp_path,
        model_override="one-time-model",
        effort_override=effort,
    )

    assert "--effort" not in spec.argv
    assert "--reasoning-effort" not in spec.argv
    if app is AppKind.CLAUDE:
        assert spec.argv == ("native-cli", "--permission-mode", "bypassPermissions")
        assert spec.env["ANTHROPIC_MODEL"] == "one-time-model"
        assert spec.env["CLAUDE_CODE_EFFORT_LEVEL"] == effort
    elif app is AppKind.CODEX:
        profile_name = spec.argv[spec.argv.index("--profile") + 1]
        assert spec.argv == ("native-cli", "--profile", profile_name)
        profile = Path(spec.env["CODEX_HOME"]) / f"{profile_name}.config.toml"
        profile_text = profile.read_text(encoding="utf-8")
        assert 'model = "one-time-model"' in profile_text
        assert f'model_reasoning_effort = "{effort}"' in profile_text
    else:
        profile_name = spec.argv[spec.argv.index("--model") + 1]
        assert spec.argv == (
            "native-cli",
            "--model",
            profile_name,
            "--sandbox",
            "workspace",
            "--always-approve",
        )
        document = tomlkit.parse(
            (Path(spec.env["GROK_HOME"]) / "config.toml").read_text(encoding="utf-8")
        )
        assert document["model"][profile_name]["model"] == "one-time-model"
        assert document["models"]["default_reasoning_effort"] == effort


def test_launch_rejects_invalid_codex_effort(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")

    with pytest.raises(ProviderError, match="Invalid codex effort"):
        build_launch_spec(
            _provider(AppKind.CODEX),
            _settings(tmp_path),
            tmp_path,
            effort_override="max",
        )


def test_codex_resume_uses_session_cwd_and_resume_subcommand(tmp_path, monkeypatch) -> None:
    from ccs_plus.sessions import Session

    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    work = tmp_path / "session-work"
    work.mkdir()
    session = Session(
        app=AppKind.CODEX,
        session_id="sid-123",
        title="resume me",
        cwd=str(work),
        modified_at=1.0,
    )

    spec = build_launch_spec(
        _provider(AppKind.CODEX),
        _settings(tmp_path),
        tmp_path,
        resume=session,
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert spec.cwd == work.resolve()
    assert spec.argv[0:3] == ("native-codex", "resume", "sid-123")
    assert "--profile" in spec.argv
    profile_name = spec.argv[spec.argv.index("--profile") + 1]
    profile_text = (Path(spec.env["CODEX_HOME"]) / f"{profile_name}.config.toml").read_text(
        encoding="utf-8"
    )
    assert 'approval_policy = "on-request"' in profile_text
    assert 'default_permissions = ":workspace"' in profile_text


def test_claude_resume_adds_resume_flag(tmp_path, monkeypatch) -> None:
    from ccs_plus.sessions import Session

    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-claude")
    work = tmp_path / "claude-work"
    work.mkdir()
    session = Session(
        app=AppKind.CLAUDE,
        session_id="claude-sid",
        title="hello",
        cwd=str(work),
        modified_at=1.0,
    )

    spec = build_launch_spec(
        _provider(AppKind.CLAUDE),
        _settings(tmp_path),
        tmp_path,
        resume=session,
    )

    assert spec.argv[0:3] == ("native-claude", "--resume", "claude-sid")
    assert spec.cwd == work.resolve()


def test_official_claude_does_not_inherit_custom_route(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-claude")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://stale.example.test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "stale-secret-key")
    official = Provider(
        id="claude-official",
        app=AppKind.CLAUDE,
        name="Claude official",
        settings_config={},
        endpoints=(),
        category="official",
        created_at=None,
        notes=None,
        is_current=False,
    )

    spec = build_launch_spec(official, _settings(tmp_path), tmp_path)

    assert "ANTHROPIC_BASE_URL" not in spec.env
    assert "ANTHROPIC_AUTH_TOKEN" not in spec.env


def test_launch_returns_child_exit_code(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class Completed:
        returncode = 7

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("ccs_plus.launcher.subprocess.run", fake_run)
    spec = LaunchSpec(argv=("native-cli",), cwd=tmp_path, env={})
    assert launch(spec) == 7
    assert captured["kwargs"] == {"cwd": tmp_path, "env": {}, "check": False}


def test_codex_launch_links_skills_and_merges_user_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    user_home = tmp_path / "user-codex"
    (user_home / "skills" / "pomelo-db").mkdir(parents=True)
    (user_home / "skills" / ".system").mkdir()
    (user_home / "plugins" / "cache").mkdir(parents=True)
    (user_home / "config.toml").write_text(
        """
[mcp_servers.mks-ttyd]
command = "mks-ttyd"
""",
        encoding="utf-8",
    )
    settings = make_app_settings(tmp_path, codex_user_home=user_home)

    spec = build_launch_spec(_provider(AppKind.CODEX), settings, tmp_path)

    app_home = Path(spec.env["CODEX_HOME"])
    skills = app_home / "skills"
    assert (skills / "pomelo-db").exists()
    assert not (skills / ".system").exists()
    assert (app_home / "plugins" / "cache").exists()
    profile_name = spec.argv[spec.argv.index("--profile") + 1]
    profile_text = (app_home / f"{profile_name}.config.toml").read_text(encoding="utf-8")
    assert "mks-ttyd" in profile_text


def test_codex_direct_launch_links_and_merges_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    user_home = tmp_path / "user-codex"
    (user_home / "skills" / "specflow").mkdir(parents=True)
    (user_home / "config.toml").write_text(
        """
[mcp_servers.mks-ttyd]
command = "mks-ttyd"
""",
        encoding="utf-8",
    )
    settings = make_app_settings(tmp_path, codex_user_home=user_home)
    official = Provider(
        id="codex-official",
        app=AppKind.CODEX,
        name="Codex official",
        settings_config={},
        endpoints=(),
        category="official",
        created_at=None,
        notes=None,
        is_current=False,
    )

    spec = build_launch_spec(official, settings, tmp_path)
    app_home = Path(spec.env["CODEX_HOME"])

    assert (app_home / "skills" / "specflow").exists()
    document = tomlkit.parse((app_home / "config.toml").read_text(encoding="utf-8"))
    assert document["mcp_servers"]["mks-ttyd"]["command"] == "mks-ttyd"
    assert not list(app_home.glob("ccs-plus-codex-*.config.toml"))


def test_codex_launch_copies_current_project_trust_for_mcp(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    user_home = tmp_path / "user-codex"
    user_home.mkdir()
    (user_home / "config.toml").write_text(
        f"""
[projects.'{tmp_path.as_posix()}']
trust_level = "trusted"

[mcp_servers.demo]
command = "demo"
""",
        encoding="utf-8",
    )
    settings = make_app_settings(tmp_path, codex_user_home=user_home)
    official = Provider(
        id="codex-official",
        app=AppKind.CODEX,
        name="Codex official",
        settings_config={},
        endpoints=(),
        category="official",
        created_at=None,
        notes=None,
        is_current=False,
    )

    build_launch_spec(official, settings, tmp_path)

    document = tomlkit.parse((settings.codex.home / "config.toml").read_text(encoding="utf-8"))
    assert document["projects"][tmp_path.as_posix()]["trust_level"] == "trusted"


def test_codex_launch_copies_ancestor_project_trust_for_mcp(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-codex")
    project = tmp_path / "repo"
    working_directory = project / "src"
    working_directory.mkdir(parents=True)
    user_home = tmp_path / "user-codex"
    user_home.mkdir()
    (user_home / "config.toml").write_text(
        f"""
[projects.'{project.as_posix()}']
trust_level = "trusted"
""",
        encoding="utf-8",
    )
    settings = make_app_settings(tmp_path, codex_user_home=user_home)
    official = Provider(
        id="codex-official",
        app=AppKind.CODEX,
        name="Codex official",
        settings_config={},
        endpoints=(),
        category="official",
        created_at=None,
        notes=None,
        is_current=False,
    )

    build_launch_spec(official, settings, working_directory)

    document = tomlkit.parse((settings.codex.home / "config.toml").read_text(encoding="utf-8"))
    assert document["projects"][project.as_posix()]["trust_level"] == "trusted"


@pytest.mark.parametrize("app", (AppKind.CODEX, AppKind.GROK))
def test_launch_specs_share_the_app_home_across_providers(tmp_path, monkeypatch, app) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-cli")
    settings = _settings(tmp_path)
    first = _provider(
        app,
        name="First Provider",
        endpoint="https://first.example.test/v1",
        model="first-model",
    )
    second = _provider(
        app,
        name="Second Provider",
        endpoint="https://second.example.test/v1",
        model="second-model",
    )

    first_spec = build_launch_spec(first, settings, tmp_path)
    second_spec = build_launch_spec(second, settings, tmp_path)

    home_key = "CODEX_HOME" if app is AppKind.CODEX else "GROK_HOME"
    first_home = Path(first_spec.env[home_key])
    second_home = Path(second_spec.env[home_key])
    shared = settings.state_home(app.value) / "sessions"
    assert first_home == shared.parent
    assert second_home == shared.parent
    if app is AppKind.CODEX:
        sessions = first_home / "sessions"
        assert sessions.is_dir()
        assert _is_link(sessions)
        assert _links_to(sessions, settings.codex.user_home / "sessions")
        assert "CODEX_SQLITE_HOME" not in first_spec.env
        assert "CODEX_SQLITE_HOME" not in second_spec.env
        first_profile = first_spec.argv[first_spec.argv.index("--profile") + 1]
        second_profile = second_spec.argv[second_spec.argv.index("--profile") + 1]
        assert first_profile != second_profile
        first_document = tomlkit.parse(
            (first_home / f"{first_profile}.config.toml").read_text(encoding="utf-8")
        )
        second_document = tomlkit.parse(
            (second_home / f"{second_profile}.config.toml").read_text(encoding="utf-8")
        )
        assert first_document["model_provider"] == settings.codex.session_model_provider
        assert second_document["model_provider"] == settings.codex.session_model_provider
        assert "--model" not in first_spec.argv
        assert "--ask-for-approval" not in first_spec.argv


def test_claude_launch_links_and_syncs_mcp(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-claude")
    user_home = tmp_path / "user-claude"
    (user_home / "skills" / "housekeeper").mkdir(parents=True)
    (user_home / "plugins" / "marketplaces").mkdir(parents=True)
    source = tmp_path / "user.claude.json"
    source.write_text(
        json.dumps({"mcpServers": {"demo": {"command": "demo"}}}),
        encoding="utf-8",
    )
    settings = make_app_settings(tmp_path, claude_user_home=user_home)
    monkeypatch.setattr(
        "ccs_plus.home_visibility.Path.home",
        classmethod(lambda cls: tmp_path),
    )
    # sync reads Path.home() / ".claude.json"; place source there.
    (tmp_path / ".claude.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    build_launch_spec(_provider(AppKind.CLAUDE), settings, tmp_path)

    assert (settings.claude.home / "skills" / "housekeeper").exists()
    assert (settings.claude.home / "plugins" / "marketplaces").exists()
    document = json.loads((settings.claude.home / ".claude.json").read_text(encoding="utf-8"))
    assert document["mcpServers"]["demo"]["command"] == "demo"


def test_grok_launch_does_not_link_user_skills(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ccs_plus.launcher.shutil.which", lambda _: "native-grok")
    user_like = tmp_path / "user-grok" / "skills" / "x"
    user_like.mkdir(parents=True)
    settings = make_app_settings(tmp_path)

    build_launch_spec(_provider(AppKind.GROK), settings, tmp_path)

    assert not (settings.grok.home / "skills").exists()


def test_launch_logs_argv_and_exit_code_without_environment(monkeypatch, tmp_path, caplog) -> None:
    class Completed:
        returncode = 0

    monkeypatch.setattr("ccs_plus.launcher.subprocess.run", lambda *args, **kwargs: Completed())
    spec = LaunchSpec(
        argv=("native-cli", "--model", "example-model"),
        cwd=tmp_path,
        env={"API_KEY": "launch-secret-key"},
    )
    caplog.set_level(logging.INFO, logger="ccs_plus.launcher")

    assert launch(spec) == 0
    assert "native-cli" in caplog.text
    assert "Native CLI exited with code 0" in caplog.text
    assert "launch-secret-key" not in caplog.text
