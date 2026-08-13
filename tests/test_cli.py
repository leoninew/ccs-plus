from __future__ import annotations

import json
import logging
from dataclasses import replace

from click.testing import CliRunner
from conftest import make_app_settings

from ccs_plus.adapters import build_provider
from ccs_plus.cli import main
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, Provider
from ccs_plus.launch_history import LaunchHistory
from ccs_plus.launcher import LaunchSpec
from ccs_plus.settings import AppSettings

_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _provider():
    return build_provider(
        NewProvider(
            app=AppKind.CLAUDE,
            name="Example Provider",
            endpoint="https://api.example.test/v1",
            api_key="cli-secret-key",
            model="example-model",
            effort="high",
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
    assert "-v, --verbose" in result.output


def test_launch_selects_provider_by_name(monkeypatch, tmp_path) -> None:
    provider = _provider()
    settings = _settings(tmp_path)
    selected = []

    class Repository:
        def __init__(self, database_path):
            assert database_path == settings.database_path

        def get_by_name(self, app, name):
            selected.append((app, name))
            return provider

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli.ProviderRepository", Repository)
    monkeypatch.setattr(
        "ccs_plus.cli.build_launch_spec",
        lambda provider, settings, cwd, model_override, effort_override: LaunchSpec(
            argv=("native-cli",), cwd=tmp_path, env={}
        ),
    )
    monkeypatch.setattr("ccs_plus.cli.launch", lambda spec: 0)

    result = CliRunner().invoke(
        main,
        ["launch", "claude", "--provider", provider.name, "--cwd", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert selected == [(AppKind.CLAUDE, provider.name)]


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
    provider = _provider()
    settings = _settings(tmp_path)
    launched = []

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
        lambda selected, current_settings, cwd: LaunchSpec(argv=("native-cli",), cwd=cwd, env={}),
    )
    monkeypatch.setattr("ccs_plus.cli.launch", lambda spec: launched.append(spec) or 0)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, input="1\n1\n\ny\n")

    assert result.exit_code == 0
    assert "Start an agent" in result.output
    assert "Example Provider" in result.output
    assert len(launched) == 1
    history = LaunchHistory.load(tmp_path / "data" / "launch-history.json")
    assert history.default_provider_id(AppKind.CLAUDE, [provider]) == provider.id


def test_no_argument_launch_can_be_cancelled(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("ccs_plus.cli._settings", lambda: _settings(tmp_path))

    result = CliRunner().invoke(main, input="q\n")

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


def test_provider_export_writes_default_encrypted_backup(monkeypatch, tmp_path) -> None:
    provider = _provider()
    settings = _settings(tmp_path)

    class Repository:
        def list_stored(self):
            return [provider]

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: settings)
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "export"])

    assert result.exit_code == 0
    assert "Exported 1 custom providers" in result.output
    output_path = next((tmp_path / "data").glob("providers-*.json"))
    assert "cli-secret-key" not in output_path.read_text(encoding="utf-8")


def test_provider_export_preserves_stored_provider_order(monkeypatch, tmp_path) -> None:
    first = replace(_provider(), name="First")
    second = replace(_provider(), name="Second")
    settings = _settings(tmp_path)
    output_path = tmp_path / "providers.json"

    class Repository:
        def list_stored(self):
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


def test_provider_import_validates_before_writing(monkeypatch, tmp_path) -> None:
    from ccs_plus.provider_transfer import build_backup_document

    document = build_backup_document([_provider()], "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    document["providers"][0]["endpoint"] = "not-a-url"
    input_path = tmp_path / "providers.json"
    input_path.write_text(json.dumps(document), encoding="utf-8")
    added = []

    class Repository:
        def list(self):
            return []

        def add_many(self, providers):
            added.extend(providers)

    monkeypatch.setattr("ccs_plus.cli._settings", lambda: _settings(tmp_path))
    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())
    monkeypatch.setattr(
        "ccs_plus.cli._encryption_key", lambda: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )

    result = CliRunner().invoke(main, ["providers", "import", str(input_path)])

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
        def list(self):
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


def test_provider_reset_defaults_to_dry_run(monkeypatch) -> None:
    provider = _provider()

    class Repository:
        def list(self):
            return [provider]

        def reset_non_official(self):
            raise AssertionError("Dry run must not delete providers.")

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())

    result = CliRunner().invoke(main, ["providers", "reset"])

    assert result.exit_code == 0
    assert "would delete 1 non-official provider" in result.output
    assert "claude/Example Provider" in result.output


def test_provider_reset_deletes_non_official_providers(monkeypatch) -> None:
    deleted = []

    class Repository:
        def list(self):
            return []

        def reset_non_official(self):
            deleted.append(True)
            return 2

    monkeypatch.setattr("ccs_plus.cli._repository", lambda: Repository())

    result = CliRunner().invoke(main, ["providers", "reset", "--no-dry-run"])

    assert result.exit_code == 0
    assert deleted == [True]
    assert result.output == "Deleted 2 non-official providers.\n"


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
