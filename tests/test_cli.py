from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest
from click.testing import CliRunner
from conftest import make_app_settings

from ccs_plus.adapters import build_provider
from ccs_plus.cli import main
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, Provider
from ccs_plus.launch_history import LaunchHistory
from ccs_plus.launcher import LaunchSpec
from ccs_plus.settings import AppSettings

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _provider(app: AppKind = AppKind.CLAUDE, name: str = "Example Provider") -> Provider:
    return build_provider(
        NewProvider(
            app=app,
            name=name,
            endpoint="https://api.example.test/v1",
            api_key="cli-secret-key",
            model="example-model",
            effort="xhigh" if app is AppKind.GROK else "high",
            notes=None,
        ),
        _CODEX,
    )


def _settings(tmp_path, **overrides) -> AppSettings:
    return make_app_settings(tmp_path, **overrides)


def test_help_exposes_provider_and_launch_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "providers" in result.output
    assert "launch" in result.output
    assert "run" in result.output


def test_short_help_option_matches_long_help_for_every_command() -> None:
    runner = CliRunner()
    commands = (
        (),
        ("providers",),
        ("providers", "list"),
        ("providers", "add"),
        ("providers", "export"),
        ("providers", "import"),
        ("providers", "reset"),
        ("providers", "show"),
        ("providers", "delete"),
        ("launch",),
        ("run",),
    )
    for command in commands:
        short_help = runner.invoke(main, [*command, "-h"])
        long_help = runner.invoke(main, [*command, "--help"])

        assert short_help.exit_code == long_help.exit_code == 0
        assert short_help.output == long_help.output


def test_launch_help_makes_cwd_optional() -> None:
    result = CliRunner().invoke(main, ["launch", "--help"])
    assert result.exit_code == 0
    assert "--cwd DIRECTORY  [required]" not in result.output
    assert "--model TEXT" in result.output
    assert "--effort TEXT" in result.output
    assert "-v, --verbose" in result.output


def test_launch_selects_provider_by_name(monkeypatch, tmp_path) -> None:
    provider = _provider()
    settings = _settings(tmp_path)
    selected = []
    built = []

    class Repository:
        def __init__(self, database_path):
            assert database_path == settings.database_path

        def get_by_name(self, app, name):
            selected.append((app, name))
            return provider

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)

    def fake_build_launch_spec(provider, settings, cwd, model_override, effort_override):
        built.append((provider, settings, cwd, model_override, effort_override))
        return LaunchSpec(argv=("native-cli",), cwd=tmp_path, env={})

    monkeypatch.setattr("ccs_plus.cli.build_launch_spec", fake_build_launch_spec)
    monkeypatch.setattr("ccs_plus.cli.launch", lambda spec: 0)

    result = CliRunner().invoke(
        main,
        [
            "launch",
            "claude",
            "--provider",
            provider.name,
            "--cwd",
            str(tmp_path),
            "--model",
            "one-time-model",
            "--effort",
            "low",
        ],
    )

    assert result.exit_code == 0
    assert selected == [(AppKind.CLAUDE, provider.name)]
    assert built == [(provider, settings, tmp_path, "one-time-model", "low")]


def test_run_selects_provider_by_list_number(monkeypatch, tmp_path) -> None:
    first = _provider(AppKind.CODEX, "First Codex")
    second = _provider(AppKind.CODEX, "Second Codex")
    settings = _settings(tmp_path)
    built = []

    class Repository:
        def __init__(self, database_path):
            assert database_path == settings.database_path

        def list(self, apps):
            assert apps == [AppKind.CODEX]
            return [first, second]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)

    def fake_build_launch_spec(provider, current_settings, cwd, model_override, effort_override):
        built.append((provider, current_settings, cwd, model_override, effort_override))
        return LaunchSpec(argv=("native-cli",), cwd=tmp_path, env={})

    monkeypatch.setattr("ccs_plus.cli.build_launch_spec", fake_build_launch_spec)
    monkeypatch.setattr("ccs_plus.cli.launch", lambda spec: 0)

    result = CliRunner().invoke(main, ["run", "X2"])

    assert result.exit_code == 0
    assert built == [(second, settings, None, None, None)]


@pytest.mark.parametrize("target", ("codex1", "c0", "x", "z1"))
def test_run_rejects_invalid_target(target: str) -> None:
    result = CliRunner().invoke(main, ["run", target])

    assert result.exit_code != 0
    assert "Run target must be c, x, or g" in result.output


def test_run_rejects_unknown_list_number(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path)

    class Repository:
        def __init__(self, database_path):
            assert database_path == settings.database_path

        def list(self, apps):
            assert apps == [AppKind.GROK]
            return []

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)
    monkeypatch.setattr(
        "ccs_plus.cli.build_launch_spec",
        lambda *args: (_ for _ in ()).throw(AssertionError("run must not launch")),
    )

    result = CliRunner().invoke(main, ["run", "g1"])

    assert result.exit_code != 0
    assert "Provider number 1 does not exist for grok" in result.output


def test_run_verbose_configures_logging_and_does_not_log_api_key(
    monkeypatch, tmp_path, caplog
) -> None:
    provider = _provider(AppKind.CLAUDE)
    settings = _settings(tmp_path)
    logging_options = []

    class Repository:
        def __init__(self, database_path):
            assert database_path == settings.database_path

        def list(self, apps):
            assert apps == [AppKind.CLAUDE]
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)
    monkeypatch.setattr(
        "ccs_plus.cli.build_launch_spec",
        lambda provider, settings, cwd, model_override, effort_override: LaunchSpec(
            argv=("native-cli",), cwd=tmp_path, env={"API_KEY": "cli-secret-key"}
        ),
    )
    monkeypatch.setattr("ccs_plus.cli.launch", lambda spec: 0)
    monkeypatch.setattr(
        "ccs_plus.cli.logging.basicConfig", lambda **kwargs: logging_options.append(kwargs)
    )
    caplog.set_level(logging.INFO, logger="ccs_plus.cli")

    result = CliRunner().invoke(main, ["run", "-v", "c1"])

    assert result.exit_code == 0
    assert logging_options == [
        {
            "level": logging.INFO,
            "format": "%(levelname)s %(name)s: %(message)s",
            "force": True,
        }
    ]
    assert "Launching claude with provider" in caplog.text
    assert "cli-secret-key" not in caplog.text


def test_launch_verbose_configures_logging_and_does_not_log_api_key(
    monkeypatch, tmp_path, caplog
) -> None:
    provider = _provider()
    settings = _settings(tmp_path)
    logging_options = []

    class Repository:
        def __init__(self, database_path):
            assert database_path == settings.database_path

        def get_by_name(self, app, name):
            return provider

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)
    monkeypatch.setattr(
        "ccs_plus.cli.build_launch_spec",
        lambda provider, settings, cwd, model_override, effort_override: LaunchSpec(
            argv=("native-cli",), cwd=tmp_path, env={"API_KEY": "cli-secret-key"}
        ),
    )
    monkeypatch.setattr("ccs_plus.cli.launch", lambda spec: 0)
    monkeypatch.setattr(
        "ccs_plus.cli.logging.basicConfig", lambda **kwargs: logging_options.append(kwargs)
    )
    caplog.set_level(logging.INFO, logger="ccs_plus.cli")

    result = CliRunner().invoke(main, ["launch", "claude", "--provider", provider.name, "-v"])

    assert result.exit_code == 0
    assert logging_options == [
        {
            "level": logging.INFO,
            "format": "%(levelname)s %(name)s: %(message)s",
            "force": True,
        }
    ]
    assert "Launching claude with provider" in caplog.text
    assert "cli-secret-key" not in caplog.text


def test_no_argument_launch_uses_interactive_selection_and_records_history(
    monkeypatch, tmp_path
) -> None:
    from ccs_plus.tui import LaunchPlan

    provider = _provider()
    settings = _settings(tmp_path)
    launched = []

    class Repository:
        def __init__(self, database_path):
            assert database_path == settings.database_path

        def list(self, apps):
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)
    monkeypatch.setattr(
        "ccs_plus.cli.build_launch_spec",
        lambda selected, current_settings, cwd, **kwargs: LaunchSpec(
            argv=("native-cli",), cwd=cwd, env={}
        ),
    )
    monkeypatch.setattr("ccs_plus.cli.launch", lambda spec: launched.append(spec) or 0)
    monkeypatch.setattr(
        "ccs_plus.cli._run_launcher",
        lambda settings, providers, history: LaunchPlan(
            provider=provider,
            cwd=tmp_path,
            session=None,
            approval_policy=None,
            sandbox_mode=None,
        ),
    )

    result = CliRunner().invoke(main)

    assert result.exit_code == 0
    assert len(launched) == 1
    history = LaunchHistory.load(tmp_path / "data" / "launch-history.json")
    assert history.default_provider_id(AppKind.CLAUDE, [provider]) == provider.id


def test_no_argument_launch_can_be_cancelled(monkeypatch, tmp_path) -> None:
    provider = _provider()
    settings = _settings(tmp_path)

    class Repository:
        def __init__(self, database_path):
            pass

        def list(self, apps):
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)
    monkeypatch.setattr("ccs_plus.cli._run_launcher", lambda settings, providers, history: None)

    result = CliRunner().invoke(main)

    assert result.exit_code == 0
    assert result.output.count("Cancelled.") == 1


def test_provider_list_json_does_not_expose_api_key(monkeypatch) -> None:
    provider = replace(_provider(), endpoints=("https://stale.example.test/v1",))

    class Repository:
        def list(self, apps):
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(main, ["providers", "list", "--json"])
    assert result.exit_code == 0
    assert provider.id not in result.output
    assert "cli-secret-key" not in result.output
    assert "https://api.example.test/v1" in result.output
    assert "https://stale.example.test/v1" not in result.output
    assert '"reasoning_effort": "high"' in result.output
    assert '"is_current"' not in result.output
    record = json.loads(result.output)[0]
    assert record["shortcut"] == "ccs-plus run c1"
    assert "number" not in record
    assert "run" not in record


def test_provider_list_numbers_each_app_from_one(monkeypatch) -> None:
    records = [
        _provider(AppKind.CLAUDE, "Claude 1"),
        _provider(AppKind.CLAUDE, "Claude 2"),
        _provider(AppKind.CODEX, "Codex 1"),
        _provider(AppKind.GROK, "Grok 1"),
    ]

    class Repository:
        def list(self, apps):
            assert apps == list(AppKind)
            return records

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(main, ["providers", "list", "--json"])

    assert result.exit_code == 0
    assert [record["shortcut"] for record in json.loads(result.output)] == [
        "ccs-plus run c1",
        "ccs-plus run c2",
        "ccs-plus run x1",
        "ccs-plus run g1",
    ]


def test_provider_list_renders_alias_after_name_without_shortcut_column(monkeypatch) -> None:
    provider = _provider(AppKind.CODEX, "Codex 1")

    class Repository:
        def list(self, apps):
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(main, ["providers", "list"])

    assert result.exit_code == 0
    assert "Alias" in result.output
    assert result.output.index("Name") < result.output.index("Alias")
    assert "x1" in result.output
    assert "Shortcut" not in result.output
    assert "ccs-plus run x1" not in result.output


def test_provider_list_falls_back_to_endpoint_candidates(monkeypatch) -> None:
    provider = Provider(
        id="legacy-provider",
        app=AppKind.CODEX,
        name="Legacy provider",
        settings_config={"config": "model_provider = ["},
        endpoints=("https://candidate.example.test/v1",),
        category="custom",
        created_at=None,
        notes=None,
        is_current=False,
    )

    class Repository:
        def list(self, apps):
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(main, ["providers", "list", "--json"])

    assert result.exit_code == 0
    assert "https://candidate.example.test/v1" in result.output


def test_provider_add_does_not_echo_api_key(monkeypatch, tmp_path) -> None:
    added = []

    class Repository:
        def add(self, provider):
            added.append(provider)

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(
        main,
        [
            "providers",
            "add",
            "codex",
            "--name",
            "Example Provider",
            "--endpoint",
            "https://api.example.test/v1",
            "--api-key",
            "add-secret-key",
            "--model",
            "example-model",
            "--effort",
            "high",
        ],
    )

    assert result.exit_code == 0
    assert len(added) == 1
    assert added[0].app is AppKind.CODEX
    assert "add-secret-key" not in result.output
    config = added[0].settings_config["config"]
    assert 'sandbox_mode = "danger-full-access"' in config
    assert 'approval_policy = "never"' in config


def test_provider_add_grok_writes_default_reasoning_effort(monkeypatch, tmp_path) -> None:
    added = []

    class Repository:
        def add(self, provider):
            added.append(provider)

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(
        main,
        [
            "providers",
            "add",
            "grok",
            "--name",
            "Grok Provider",
            "--endpoint",
            "https://api.example.test/v1",
            "--api-key",
            "add-secret-key",
            "--model",
            "grok-4.5",
            "--effort",
            "xhigh",
        ],
    )

    assert result.exit_code == 0
    config = added[0].settings_config["config"]
    assert 'default_reasoning_effort = "xhigh"' in config


def test_provider_export_writes_default_encrypted_backup(monkeypatch, tmp_path) -> None:
    provider = _provider()
    settings = _settings(tmp_path)

    class Repository:
        def list_stored(self, apps):
            assert apps == list(AppKind)
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "export"])

    assert result.exit_code == 0
    assert "Exported 1 custom providers" in result.output
    output_path = next((tmp_path / "data").glob("providers-all-*.json"))
    assert "cli-secret-key" not in output_path.read_text(encoding="utf-8")


def test_provider_export_preserves_stored_provider_order(monkeypatch, tmp_path) -> None:
    first = replace(_provider(), name="First")
    second = replace(_provider(), name="Second")
    settings = _settings(tmp_path)
    output_path = tmp_path / "providers.json"

    class Repository:
        def list_stored(self, apps):
            assert apps == list(AppKind)
            return [second, first]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "export", str(output_path)])

    assert result.exit_code == 0
    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert [record["name"] for record in document["providers"]] == ["Second", "First"]


def test_provider_export_limits_backup_to_selected_app(monkeypatch, tmp_path) -> None:
    codex = _provider(AppKind.CODEX, "Codex Provider")
    output_path = tmp_path / "providers.json"

    class Repository:
        def list_stored(self, apps):
            assert apps == [AppKind.CODEX]
            return [codex]

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "export", "codex", str(output_path)])

    assert result.exit_code == 0
    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert [record["app"] for record in document["providers"]] == ["codex"]


def test_provider_export_uses_app_name_in_default_backup_filename(monkeypatch, tmp_path) -> None:
    provider = _provider(AppKind.CODEX)
    settings = _settings(tmp_path)

    class Repository:
        def list_stored(self, apps):
            assert apps == [AppKind.CODEX]
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "export", "codex"])

    assert result.exit_code == 0
    assert len(list((tmp_path / "data").glob("providers-codex-*.json"))) == 1


def test_provider_import_validates_complete_backup_before_filtering(monkeypatch, tmp_path) -> None:
    from ccs_plus.provider_transfer import build_backup_document

    document = build_backup_document(
        [_provider(AppKind.CODEX), _provider(AppKind.CLAUDE)],
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    document["providers"][1]["endpoint"] = "not-a-url"
    input_path = tmp_path / "providers.json"
    input_path.write_text(json.dumps(document), encoding="utf-8")
    added = []

    class Repository:
        def list(self, apps):
            raise AssertionError("Invalid backups must fail before checking existing providers.")

        def add_many(self, providers):
            added.extend(providers)

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "import", "codex", str(input_path)])

    assert result.exit_code != 0
    assert "Endpoint must be an absolute http or https URL" in result.output
    assert added == []


def test_provider_import_adds_all_validated_providers(monkeypatch, tmp_path) -> None:
    from ccs_plus.provider_transfer import build_backup_document

    input_path = tmp_path / "providers.json"
    input_path.write_text(
        json.dumps(
            build_backup_document([_provider()], "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
        ),
        encoding="utf-8",
    )
    added = []

    class Repository:
        def list(self, apps):
            assert apps == list(AppKind)
            return []

        def add_many(self, providers):
            added.extend(providers)

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "import", str(input_path)])

    assert result.exit_code == 0
    assert "Imported 1 custom providers" in result.output
    assert len(added) == 1
    assert added[0].name == "Example Provider"


def test_provider_import_limits_records_to_selected_app(monkeypatch, tmp_path) -> None:
    from ccs_plus.provider_transfer import build_backup_document

    codex = _provider(AppKind.CODEX, "Codex Provider")
    claude = _provider(AppKind.CLAUDE, "Claude Provider")
    input_path = tmp_path / "providers.json"
    input_path.write_text(
        json.dumps(
            build_backup_document([codex, claude], "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
        ),
        encoding="utf-8",
    )
    added = []

    class Repository:
        def list(self, apps):
            assert apps == [AppKind.CODEX]
            return []

        def add_many(self, providers):
            added.extend(providers)

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "import", "codex", str(input_path)])

    assert result.exit_code == 0
    assert "Imported 1 custom providers" in result.output
    assert [(provider.app, provider.name) for provider in added] == [
        (AppKind.CODEX, "Codex Provider")
    ]


def test_provider_reset_defaults_to_dry_run(monkeypatch) -> None:
    provider = _provider()

    class Repository:
        def list(self, apps):
            assert apps == list(AppKind)
            return [provider]

        def reset_non_official(self, apps):
            raise AssertionError("Dry run must not delete providers.")

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())

    result = CliRunner().invoke(main, ["providers", "reset"])

    assert result.exit_code == 0
    assert "would delete 1 non-official provider" in result.output
    assert "claude/Example Provider" in result.output


def test_provider_reset_deletes_all_non_official_providers_by_default(monkeypatch) -> None:
    deleted = []

    class Repository:
        def list(self, apps):
            assert apps == list(AppKind)
            return []

        def reset_non_official(self, apps):
            deleted.append(apps)
            return 2

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())

    result = CliRunner().invoke(main, ["providers", "reset", "--no-dry-run"])

    assert result.exit_code == 0
    assert deleted == [list(AppKind)]
    assert result.output == "Deleted 2 non-official providers.\n"


def test_provider_reset_removes_deleted_codex_profiles(monkeypatch, tmp_path) -> None:
    codex = _provider(AppKind.CODEX, "Codex")
    claude = _provider(AppKind.CLAUDE, "Claude")
    settings = _settings(tmp_path)
    removed = []

    class Repository:
        def list(self, apps):
            assert apps == [AppKind.CODEX]
            return [codex, claude]

        def reset_non_official(self, apps):
            assert apps == [AppKind.CODEX]
            return 2

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr(
        "ccs_plus.cli.remove_managed_config",
        lambda home, provider_id: removed.append((home, provider_id)),
    )

    result = CliRunner().invoke(main, ["providers", "reset", "codex", "--no-dry-run"])

    assert result.exit_code == 0
    assert removed == [(settings.codex.home, codex.id)]


def test_provider_show_includes_unredacted_key_configuration(monkeypatch) -> None:
    provider = _provider()

    class Repository:
        def find_by_name(self, name):
            assert name == provider.name
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(main, ["providers", "show", provider.name])

    assert result.exit_code == 0
    assert "cli-secret-key" in result.output
    assert "api_endpoint" in result.output
    assert list(json.loads(result.output)[0]) == [
        "api_endpoint",
        "api_key",
        "model",
        "reasoning_effort",
    ]


def test_provider_delete_requires_confirmation() -> None:
    result = CliRunner().invoke(main, ["providers", "delete", "claude", "example"])
    assert result.exit_code != 0
    assert "--yes" in result.output


def test_provider_delete_uses_the_requested_app_and_id(monkeypatch) -> None:
    deleted = []

    class Repository:
        def get_by_name(self, app, name):
            assert app is AppKind.GROK
            assert name == "Example Provider"
            return Provider(
                id="grok-provider-id",
                app=app,
                name=name,
                settings_config={},
                endpoints=(),
                category="custom",
                created_at=None,
                notes=None,
                is_current=False,
            )

        def delete(self, app, provider_id):
            deleted.append((app, provider_id))

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    result = CliRunner().invoke(main, ["providers", "delete", "grok", "Example Provider", "--yes"])

    assert result.exit_code == 0
    assert deleted == [(AppKind.GROK, "grok-provider-id")]


def test_provider_delete_removes_codex_profile(monkeypatch, tmp_path) -> None:
    provider = _provider(AppKind.CODEX, "Codex Provider")
    settings = _settings(tmp_path)
    deleted = []
    removed = []

    class Repository:
        def get_by_name(self, app, name):
            assert app is AppKind.CODEX
            assert name == provider.name
            return provider

        def delete(self, app, provider_id):
            deleted.append((app, provider_id))

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr(
        "ccs_plus.cli.remove_managed_config",
        lambda home, provider_id: removed.append((home, provider_id)),
    )

    result = CliRunner().invoke(
        main,
        ["providers", "delete", "codex", provider.name, "--yes"],
    )

    assert result.exit_code == 0
    assert deleted == [(AppKind.CODEX, provider.id)]
    assert removed == [(settings.codex.home, provider.id)]
