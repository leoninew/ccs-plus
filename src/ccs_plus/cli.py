from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ccs_plus.adapters import build_provider, display_configuration, runtime_from_provider
from ccs_plus.database import ProviderRepository
from ccs_plus.domain import AppKind, NewProvider, Provider, ProviderError, validate_new_provider
from ccs_plus.launcher import build_launch_spec, launch
from ccs_plus.provider_transfer import build_backup_document, parse_backup_document
from ccs_plus.settings import AppSettings, load_settings

logger = logging.getLogger(__name__)
HELP_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


def _settings() -> AppSettings:
    return load_settings()


def _repository() -> ProviderRepository:
    return ProviderRepository(_settings().database_path)


def _app(value: str) -> AppKind:
    return AppKind.from_cli_value(value)


@click.group(context_settings=HELP_CONTEXT_SETTINGS)
def main() -> None:
    """Manage cc-switch providers and launch native coding CLIs."""


@main.group(context_settings=HELP_CONTEXT_SETTINGS)
def providers() -> None:
    """List, add, export, import, reset, and delete cc-switch providers."""


@providers.command("list", context_settings=HELP_CONTEXT_SETTINGS)
@click.option("--app", "app_name", type=click.Choice([item.value for item in AppKind]))
@click.option("--json", "as_json", is_flag=True, help="Emit provider metadata as JSON.")
def list_providers(app_name: str | None, as_json: bool) -> None:
    """List providers without exposing API keys."""
    try:
        apps = [_app(app_name)] if app_name else list(AppKind)
        records = _repository().list(apps)
        if as_json:
            click.echo(
                json.dumps(
                    [_provider_display_record(provider) for provider in records],
                    ensure_ascii=False,
                )
            )
            return
        _render_providers(records)
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("add", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("app_name", type=click.Choice([item.value for item in AppKind]))
@click.option("--name", required=True, help="Provider display name.")
@click.option("--endpoint", required=True, help="Exact provider base URL.")
@click.option("--api-key", help="API key. Omit to enter it without terminal echo.")
@click.option("--model", required=True, help="Provider model ID.")
@click.option("--effort", help="Optional default reasoning effort.")
@click.option("--notes", help="Optional provider notes.")
def add_provider(
    app_name: str,
    name: str,
    endpoint: str,
    api_key: str | None,
    model: str,
    effort: str | None,
    notes: str | None,
) -> None:
    """Add a custom provider directly to the cc-switch database."""
    try:
        if api_key is None:
            api_key = click.prompt("API Key", hide_input=True, confirmation_prompt=False)
        value = NewProvider(
            app=_app(app_name),
            name=name,
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            effort=effort,
            notes=notes,
        )
        validate_new_provider(value)
        provider = build_provider(value)
        _repository().add(provider)
        click.echo(f"Added {provider.app.value} provider {provider.id}.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("export", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("output_path", type=click.Path(path_type=Path, dir_okay=False), required=False)
def export_providers(output_path: Path | None) -> None:
    """Write custom providers to an encrypted JSON backup."""
    try:
        output_path = output_path or _default_backup_path()
        document = build_backup_document(_repository().list(), _encryption_key())
        _write_backup(output_path, document)
        records = document["providers"]
        assert isinstance(records, list)
        click.echo(f"Exported {len(records)} custom providers to {output_path}.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("import", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("input_path", type=click.Path(path_type=Path, dir_okay=False, exists=True))
def import_providers(input_path: Path) -> None:
    """Read an encrypted JSON backup and add every validated provider."""
    try:
        document = _read_backup(input_path)
        values = parse_backup_document(document, _encryption_key())
        repository = _repository()
        _validate_import_names(values, repository.list())
        repository.add_many(build_provider(value) for value in values)
        click.echo(f"Imported {len(values)} custom providers from {input_path}.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("reset", context_settings=HELP_CONTEXT_SETTINGS)
@click.option(
    "--no-dry-run",
    is_flag=True,
    help="Delete all non-official providers instead of previewing the reset.",
)
def reset_providers(no_dry_run: bool) -> None:
    """Preview or delete every non-official provider."""
    try:
        repository = _repository()
        targets = [provider for provider in repository.list() if not provider.is_official]
        if not no_dry_run:
            count = len(targets)
            noun = "provider" if count == 1 else "providers"
            click.echo(f"Dry run: would delete {count} non-official {noun}.")
            for provider in targets:
                click.echo(f"- {provider.app.value}/{provider.name}")
            return
        deleted = repository.reset_non_official()
        click.echo(f"Deleted {deleted} non-official providers.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("show", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("name")
def show_provider(name: str) -> None:
    """Show key configuration for every exact provider-name match."""
    try:
        click.echo(
            json.dumps(
                [_provider_show_record(provider) for provider in _repository().find_by_name(name)],
                ensure_ascii=False,
                indent=2,
            )
        )
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("delete", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("app_name", type=click.Choice([item.value for item in AppKind]))
@click.argument("name")
@click.option("--yes", is_flag=True, help="Confirm permanent database deletion.")
def delete_provider(app_name: str, name: str, yes: bool) -> None:
    """Delete one custom provider and its endpoint rows from the database."""
    if not yes:
        raise click.UsageError("Pass --yes to delete a provider by name.")
    try:
        app = _app(app_name)
        repository = _repository()
        provider = repository.get_by_name(app, name)
        repository.delete(app, provider.id)
        click.echo(f"Deleted {app_name} provider {provider.name} from the database.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("launch", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("app_name", type=click.Choice([item.value for item in AppKind]))
@click.option("--provider", "provider_name", required=True, help="cc-switch provider name.")
@click.option("--cwd", type=click.Path(path_type=Path, file_okay=False))
@click.option("--model", "model_override", help="Override the model for this launch only.")
@click.option(
    "--effort", "effort_override", help="Override the reasoning effort for this launch only."
)
@click.option("-v", "--verbose", is_flag=True, help="Log launch details to standard error.")
def launch_provider(
    app_name: str,
    provider_name: str,
    cwd: Path | None,
    model_override: str | None,
    effort_override: str | None,
    verbose: bool,
) -> None:
    """Launch Claude, Codex, or Grok using one cc-switch provider."""
    try:
        if verbose:
            _configure_verbose_logging()
        app = _app(app_name)
        settings = _settings()
        provider = ProviderRepository(settings.database_path).get_by_name(app, provider_name)
        spec = build_launch_spec(provider, settings, cwd, model_override, effort_override)
        logger.info(
            "Launching %s with provider %r in %s",
            app.value,
            provider.name,
            spec.cwd,
        )
        exit_code = launch(spec)
        if exit_code:
            raise click.exceptions.Exit(exit_code)
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


def _configure_verbose_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


def _encryption_key() -> str:
    return _settings().encryption_key


def _default_backup_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = _settings().project_root / "data" / f"providers-{timestamp}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProviderError(f"Unable to create export directory {path.parent}: {exc}") from exc
    return path


def _write_backup(path: Path, document: dict[str, object]) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise ProviderError(f"Export file already exists: {path}") from exc
    except OSError as exc:
        raise ProviderError(f"Unable to write export file {path}: {exc}") from exc


def _read_backup(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError(f"Unable to read import file {path}: {exc}") from exc


def _validate_import_names(values: list[NewProvider], existing: list[Provider]) -> None:
    existing_names = {(provider.app, provider.name.strip().casefold()) for provider in existing}
    conflicts = [
        f"{value.app.value}/{value.name.strip()}"
        for value in values
        if (value.app, value.name.strip().casefold()) in existing_names
    ]
    if conflicts:
        raise ProviderError(f"Providers already exist: {', '.join(conflicts)}")


def _render_providers(
    records: list[Provider], console_factory: Callable[[], Console] = Console
) -> None:
    table = Table(title="cc-switch providers")
    for heading in ("App", "Name", "Endpoint", "Model", "Reasoning", "Category"):
        table.add_column(heading, overflow="fold")
    for provider in records:
        display = display_configuration(provider)
        endpoint = display.endpoint or (provider.endpoints[0] if provider.endpoints else "")
        category = provider.category or "custom"
        if provider.is_official:
            category = "official"
        table.add_row(
            provider.app.value,
            provider.name,
            endpoint,
            display.model or "",
            display.effort or "",
            category,
        )
    console_factory().print(table)


def _provider_display_record(provider: Provider) -> dict[str, object]:
    display = display_configuration(provider)
    return {
        "app": provider.app.value,
        "name": provider.name,
        "endpoint": display.endpoint or (provider.endpoints[0] if provider.endpoints else None),
        "model": display.model,
        "reasoning_effort": display.effort,
        "category": provider.category,
        "is_official": provider.is_official,
        "created_at": provider.created_at,
    }


def _provider_show_record(provider: Provider) -> dict[str, object]:
    display = display_configuration(provider)
    try:
        runtime = runtime_from_provider(provider)
        api_key = runtime.api_key
        model = runtime.model or display.model
        effort = runtime.effort
    except ProviderError:
        api_key = None
        model = display.model
        effort = None
    return {
        "api_endpoint": display.endpoint or (provider.endpoints[0] if provider.endpoints else None),
        "api_key": api_key,
        "model": model,
        "reasoning_effort": effort,
    }
