from __future__ import annotations

import json

import pytest

from ccs_plus.adapters import build_provider, runtime_from_provider
from ccs_plus.domain import AppKind, CodexAppConfig, NewProvider, ProviderError
from ccs_plus.provider_transfer import build_backup_document, parse_backup_document

ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
OTHER_ENCRYPTION_KEY = "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODk="
_CODEX = CodexAppConfig(approval_policy="never", sandbox_mode="danger-full-access")


def _provider(name: str = "Example Provider"):
    return build_provider(
        NewProvider(
            app=AppKind.CLAUDE,
            name=name,
            endpoint="https://api.example.test/v1",
            api_key="transfer-secret-key",
            model="example-model",
            effort="high",
            notes="Example notes",
        ),
        _CODEX,
    )


def test_backup_round_trip_encrypts_api_keys() -> None:
    document = build_backup_document([_provider()], ENCRYPTION_KEY)

    serialized = json.dumps(document)
    assert "transfer-secret-key" not in serialized
    assert document["providers"] == [
        {
            "app": "claude",
            "name": "Example Provider",
            "endpoint": "https://api.example.test/v1",
            "api_key": document["providers"][0]["api_key"],
            "model": "example-model",
            "effort": "high",
            "notes": "Example notes",
        }
    ]

    values = parse_backup_document(document, ENCRYPTION_KEY)

    assert len(values) == 1
    restored = runtime_from_provider(build_provider(values[0], _CODEX))
    assert restored.api_key == "transfer-secret-key"
    assert restored.endpoint == "https://api.example.test/v1"


def test_backup_rejects_wrong_encryption_key() -> None:
    document = build_backup_document([_provider()], ENCRYPTION_KEY)

    with pytest.raises(ProviderError, match="Unable to decrypt API key"):
        parse_backup_document(document, OTHER_ENCRYPTION_KEY)


def test_backup_rejects_duplicate_provider_names() -> None:
    document = build_backup_document([_provider(), _provider()], ENCRYPTION_KEY)

    with pytest.raises(ProviderError, match="duplicate provider"):
        parse_backup_document(document, ENCRYPTION_KEY)
