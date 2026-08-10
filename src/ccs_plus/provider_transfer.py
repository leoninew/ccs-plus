"""Encrypted provider backup serialization and validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from cryptography.fernet import Fernet, InvalidToken

from ccs_plus.adapters import runtime_from_provider
from ccs_plus.domain import AppKind, NewProvider, Provider, ProviderError, validate_new_provider

BACKUP_FORMAT = "ccs-plus.providers"
BACKUP_VERSION = 1


def build_backup_document(providers: Iterable[Provider], encryption_key: str) -> dict[str, object]:
    """Serialize exportable custom providers with Fernet-encrypted API keys."""
    fernet = _fernet(encryption_key)
    records: list[dict[str, object]] = []
    for provider in providers:
        if provider.is_official:
            continue
        try:
            runtime = runtime_from_provider(provider)
            value = NewProvider(
                app=provider.app,
                name=provider.name,
                endpoint=_required(runtime.endpoint, "endpoint"),
                api_key=_required(runtime.api_key, "API key"),
                model=_required(runtime.model, "model"),
                effort=runtime.effort,
                notes=provider.notes,
            )
            validate_new_provider(value)
        except ProviderError as exc:
            raise ProviderError(f"Cannot export provider {provider.name!r}: {exc}") from exc
        records.append(
            {
                "app": value.app.value,
                "name": value.name,
                "endpoint": value.endpoint,
                "api_key": fernet.encrypt(value.api_key.encode("utf-8")).decode("ascii"),
                "model": value.model,
                "effort": value.effort,
                "notes": value.notes,
            }
        )
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "encryption": {"algorithm": "Fernet"},
        "providers": records,
    }


def parse_backup_document(document: object, encryption_key: str) -> list[NewProvider]:
    """Decrypt, parse, and validate every provider in a backup document."""
    root = _mapping(document, "Backup document")
    _require_equal(root, "format", BACKUP_FORMAT)
    _require_equal(root, "version", BACKUP_VERSION)
    encryption = _mapping(root.get("encryption"), "Backup encryption")
    _require_equal(encryption, "algorithm", "Fernet")
    records = root.get("providers")
    if not isinstance(records, list):
        raise ProviderError("Backup providers must be a list.")

    fernet = _fernet(encryption_key)
    providers: list[NewProvider] = []
    names: set[tuple[AppKind, str]] = set()
    for index, record in enumerate(records, start=1):
        value = _parse_provider_record(record, fernet, index)
        identity = (value.app, value.name.strip().casefold())
        if identity in names:
            raise ProviderError(
                f"Backup contains duplicate provider: {value.app.value}/{value.name.strip()}."
            )
        names.add(identity)
        providers.append(value)
    return providers


def _parse_provider_record(record: object, fernet: Fernet, index: int) -> NewProvider:
    values = _mapping(record, f"Provider #{index}")
    try:
        app = AppKind.from_cli_value(_string(values.get("app"), f"Provider #{index} app"))
        api_key = _decrypt_api_key(
            fernet, _string(values.get("api_key"), f"Provider #{index} API key")
        )
        value = NewProvider(
            app=app,
            name=_string(values.get("name"), f"Provider #{index} name"),
            endpoint=_string(values.get("endpoint"), f"Provider #{index} endpoint"),
            api_key=api_key,
            model=_string(values.get("model"), f"Provider #{index} model"),
            effort=_optional_string(values.get("effort"), f"Provider #{index} effort"),
            notes=_optional_string(values.get("notes"), f"Provider #{index} notes"),
        )
        validate_new_provider(value)
        return value
    except ProviderError as exc:
        raise ProviderError(f"Invalid provider #{index}: {exc}") from exc


def _fernet(encryption_key: str) -> Fernet:
    try:
        return Fernet(encryption_key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise ProviderError("Encryption key must be a valid Fernet key.") from exc


def _decrypt_api_key(fernet: Fernet, token: str) -> str:
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise ProviderError("Unable to decrypt API key. Check the backup password.") from exc


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ProviderError(f"{label} must be an object.")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderError(f"{label} must be a non-empty string.")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderError(f"{label} must be a string or null.")
    return value


def _required(value: str | None, label: str) -> str:
    if not value:
        raise ProviderError(f"Provider {label} is missing.")
    return value


def _require_equal(values: Mapping[str, object], key: str, expected: object) -> None:
    if values.get(key) != expected:
        raise ProviderError(f"Unsupported backup {key}: {values.get(key)!r}.")
