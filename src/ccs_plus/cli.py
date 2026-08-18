from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ccs_plus import tui
from ccs_plus.adapters import build_provider, display_configuration, runtime_from_provider
from ccs_plus.database import ProviderRepository
from ccs_plus.domain import AppKind, NewProvider, Provider, ProviderError, validate_new_provider
from ccs_plus.launch_history import LaunchHistory
from ccs_plus.launcher import build_launch_spec, launch
from ccs_plus.managed_config import remove_managed_config
from ccs_plus.provider_transfer import build_backup_document, parse_backup_document
from ccs_plus.settings import AppSettings, load_settings
from ccs_plus.tui import LaunchPlan

logger = logging.getLogger(__name__)
HELP_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
RUN_APP_PREFIXES = {
    "c": AppKind.CLAUDE,
    "x": AppKind.CODEX,
    "g": AppKind.GROK,
}
RUN_PREFIXES = {app: prefix for prefix, app in RUN_APP_PREFIXES.items()}
RUN_SELECTOR = re.compile(r"(?P<app>[cxg])(?P<number>[1-9][0-9]*)", re.IGNORECASE)
APP_NAMES = frozenset(app.value for app in AppKind)


@dataclass(frozen=True)
class ProviderListEntry:
    provider: Provider
    number: int

    @property
    def run_target(self) -> str:
        return f"{RUN_PREFIXES[self.provider.app]}{self.number}"

    @property
    def shortcut(self) -> str:
        return f"ccs-plus run {self.run_target}"


def _settings() -> AppSettings:
    return load_settings()


def _repository() -> ProviderRepository:
    return ProviderRepository(_settings().database_path)


def _app(value: str) -> AppKind:
    return AppKind.from_cli_value(value)


def _selected_apps(app_name: str | None) -> list[AppKind]:
    return [_app(app_name)] if app_name else list(AppKind)


def _parse_provider_data_arguments(
    arguments: tuple[str, ...],
    *,
    command: str,
    path_label: str,
    path_required: bool,
) -> tuple[list[AppKind], Path | None]:
    """Parse ``[app] [path]`` while retaining export's legacy path-only form."""
    path_name = path_label.replace(" ", "-")
    path_usage = f"<{path_name}>" if path_required else f"[{path_name}]"
    usage = f"Usage: ccs-plus providers {command} [claude|codex|grok] {path_usage}"
    if len(arguments) > 2:
        raise click.UsageError(usage)

    app_name = arguments[0] if arguments and arguments[0] in APP_NAMES else None
    path_index = 1 if app_name else 0
    path = Path(arguments[path_index]) if len(arguments) > path_index else None

    if len(arguments) > path_index + 1:
        raise click.UsageError(usage)
    if path_required and path is None:
        raise click.UsageError(f"Missing {path_label}.")

    return _selected_apps(app_name), path


@click.group(
    context_settings=HELP_CONTEXT_SETTINGS, invoke_without_command=True, no_args_is_help=False
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Manage cc-switch providers and launch native coding CLIs."""
    if ctx.invoked_subcommand is None:
        _interactive_launch()


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
        entries = _numbered_provider_entries(records)
        if as_json:
            click.echo(
                json.dumps(
                    [_provider_display_record(entry) for entry in entries],
                    ensure_ascii=False,
                )
            )
            return
        _render_providers(entries)
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
        provider = build_provider(value, _settings().codex.provider_defaults())
        _repository().add(provider)
        click.echo(f"Added {provider.app.value} provider {provider.id}.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("export", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("arguments", nargs=-1)
def export_providers(arguments: tuple[str, ...]) -> None:
    """Write custom providers to a backup: export [app] [output-path]."""
    try:
        apps, output_path = _parse_provider_data_arguments(
            arguments,
            command="export",
            path_label="output path",
            path_required=False,
        )
        output_path = output_path or _default_backup_path(apps)
        document = build_backup_document(_repository().list_stored(apps), _encryption_key())
        _write_backup(output_path, document)
        records = document["providers"]
        assert isinstance(records, list)
        click.echo(f"Exported {len(records)} custom providers to {output_path}.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("import", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("arguments", nargs=-1)
def import_providers(arguments: tuple[str, ...]) -> None:
    """Read a backup: import [app] <input-path>."""
    try:
        apps, input_path = _parse_provider_data_arguments(
            arguments,
            command="import",
            path_label="input path",
            path_required=True,
        )
        assert input_path is not None
        document = _read_backup(input_path)
        values = parse_backup_document(document, _encryption_key())
        values = [value for value in values if value.app in apps]
        repository = _repository()
        _validate_import_names(values, repository.list(apps))
        codex = _settings().codex.provider_defaults()
        repository.add_many(build_provider(value, codex) for value in values)
        click.echo(f"Imported {len(values)} custom providers from {input_path}.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@providers.command("reset", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("app_name", type=click.Choice([item.value for item in AppKind]), required=False)
@click.option(
    "--no-dry-run",
    is_flag=True,
    help="Delete all non-official providers instead of previewing the reset.",
)
def reset_providers(app_name: str | None, no_dry_run: bool) -> None:
    """Preview or delete non-official providers for all apps or one app."""
    try:
        apps = _selected_apps(app_name)
        repository = _repository()
        targets = [provider for provider in repository.list(apps) if not provider.is_official]
        if not no_dry_run:
            count = len(targets)
            noun = "provider" if count == 1 else "providers"
            click.echo(f"Dry run: would delete {count} non-official {noun}.")
            for provider in targets:
                click.echo(f"- {provider.app.value}/{provider.name}")
            return
        deleted = repository.reset_non_official(apps)
        codex_home = _settings().codex.home
        for provider in targets:
            if provider.app.has_managed_profile_files:
                remove_managed_config(codex_home, provider.id)
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
        if provider.app.has_managed_profile_files:
            remove_managed_config(_settings().codex.home, provider.id)
        click.echo(f"Deleted {app_name} provider {provider.name} from the database.")
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("launch", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("app_name", type=click.Choice([item.value for item in AppKind]))
@click.option("--provider", "provider_name", required=True, help="cc-switch provider name.")
@click.option("--cwd", type=click.Path(path_type=Path, file_okay=False))
@click.option("--model", "model_override", help="Override the provider model for this launch.")
@click.option(
    "--effort", "effort_override", help="Override the provider reasoning effort for this launch."
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
        exit_code = _launch_selected_provider(
            provider,
            settings,
            cwd,
            model_override,
            effort_override,
        )
        if exit_code:
            raise click.exceptions.Exit(exit_code)
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("run", context_settings=HELP_CONTEXT_SETTINGS)
@click.argument("target")
@click.option("-v", "--verbose", is_flag=True, help="Log launch details to standard error.")
def run_provider(target: str, verbose: bool) -> None:
    """Launch a provider listed as c1, x1, or g1."""
    try:
        if verbose:
            _configure_verbose_logging()
        app, number = _parse_run_target(target)
        settings = _settings()
        records = ProviderRepository(settings.database_path).list([app])
        provider = _provider_at_number(app, number, _numbered_provider_entries(records))
        exit_code = _launch_selected_provider(provider, settings, None, None, None)
        if exit_code:
            raise click.exceptions.Exit(exit_code)
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


def _interactive_launch() -> None:
    """Open the multi-pane TUI launcher and hand off to the native CLI."""
    try:
        settings = _settings()
        repository = ProviderRepository(settings.database_path)
        history = LaunchHistory.load(_launch_history_path(settings))
        providers = repository.list(list(AppKind))
        if not providers:
            raise ProviderError("No providers are configured.")
        plan = _run_launcher(settings, providers, history)
        if plan is None:
            click.echo("Cancelled.")
            return
        _execute_plan(plan, settings, history)
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc


def _run_launcher(
    settings: AppSettings, providers: list[Provider], history: LaunchHistory
) -> LaunchPlan | None:
    return tui.run_launcher(settings=settings, providers=providers, history=history)


def _execute_plan(plan: LaunchPlan, settings: AppSettings, history: LaunchHistory) -> None:
    spec = build_launch_spec(
        plan.provider,
        settings,
        plan.cwd,
        resume=plan.session,
        approval_policy=plan.approval_policy,
        sandbox_mode=plan.sandbox_mode,
    )
    history.record_launch(plan.provider)
    exit_code = launch(spec)
    if exit_code:
        raise click.exceptions.Exit(exit_code)


def _launch_selected_provider(
    provider: Provider,
    settings: AppSettings,
    cwd: Path | None,
    model_override: str | None,
    effort_override: str | None,
) -> int:
    spec = build_launch_spec(provider, settings, cwd, model_override, effort_override)
    logger.info(
        "Launching %s with provider %r in %s",
        provider.app.value,
        provider.name,
        spec.cwd,
    )
    return launch(spec)


def _launch_history_path(settings: AppSettings) -> Path:
    return settings.project_root / "data" / "launch-history.json"


def _configure_verbose_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


def _encryption_key() -> str:
    return _settings().encryption_key


def _default_backup_path(apps: list[AppKind]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    scope = apps[0].value if len(apps) == 1 else "all"
    path = _settings().project_root / "data" / f"providers-{scope}-{timestamp}.json"
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


def _numbered_provider_entries(records: list[Provider]) -> list[ProviderListEntry]:
    numbers: dict[AppKind, int] = {}
    entries: list[ProviderListEntry] = []
    for provider in records:
        number = numbers.get(provider.app, 0) + 1
        numbers[provider.app] = number
        entries.append(ProviderListEntry(provider=provider, number=number))
    return entries


def _parse_run_target(value: str) -> tuple[AppKind, int]:
    match = RUN_SELECTOR.fullmatch(value.strip())
    if match is None:
        raise ProviderError(
            "Run target must be c, x, or g followed by a positive provider number "
            "(for example: x1)."
        )
    return RUN_APP_PREFIXES[match["app"].lower()], int(match["number"])


def _provider_at_number(app: AppKind, number: int, entries: list[ProviderListEntry]) -> Provider:
    for entry in entries:
        if entry.provider.app is app and entry.number == number:
            return entry.provider
    raise ProviderError(
        f"Provider number {number} does not exist for {app.value}. "
        f"Run 'ccs-plus providers list --app {app.value}' to see available providers."
    )


def _render_providers(
    entries: list[ProviderListEntry], console_factory: Callable[[], Console] = Console
) -> None:
    table = Table(title="cc-switch providers")
    for heading in ("App", "Name", "Alias", "Endpoint", "Model", "Reasoning", "Category"):
        table.add_column(heading, overflow="fold")
    for entry in entries:
        provider = entry.provider
        display = display_configuration(provider)
        endpoint = display.endpoint or (provider.endpoints[0] if provider.endpoints else "")
        category = provider.category or "custom"
        if provider.is_official:
            category = "official"
        table.add_row(
            provider.app.value,
            provider.name,
            entry.run_target,
            endpoint,
            display.model or "",
            display.effort or "",
            category,
        )
    console_factory().print(table)


def _provider_display_record(entry: ProviderListEntry) -> dict[str, object]:
    provider = entry.provider
    display = display_configuration(provider)
    return {
        "shortcut": entry.shortcut,
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
