"""Credential store 팩토리.

- credential_source == "disabled"  → MockCredentialStore (데모 계정)
- credential_source in (service_account, csv_url) → GoogleSheetCredentialStore
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.credentials.base import CredentialStore


@lru_cache
def get_credential_store() -> CredentialStore:
    settings = get_settings()
    if settings.credential_source == "disabled":
        from app.credentials.mock_store import MockCredentialStore

        return MockCredentialStore()

    from app.credentials.google_sheet_store import GoogleSheetCredentialStore

    return GoogleSheetCredentialStore(settings)


def reset_credential_store() -> None:
    """테스트/설정변경 시 캐시 초기화."""
    get_credential_store.cache_clear()
