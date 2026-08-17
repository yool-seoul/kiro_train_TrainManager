"""전역 테스트 설정.

테스트 실행 시 외부 서비스(Google Sheets, 텔레그램 등) 호출을 방지한다.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_external_services(monkeypatch):
    """모든 테스트에서 외부 서비스를 비활성화한다.

    - credential_source=disabled → Google Sheet API 호출 차단
    - notify_channel=none → 텔레그램 전송 차단
    """
    from app.config import get_settings
    from app.credentials.factory import reset_credential_store

    settings = get_settings()
    monkeypatch.setattr(settings, "credential_source", "disabled")
    monkeypatch.setattr(settings, "notify_channel", "none")
    reset_credential_store()
    yield
    reset_credential_store()
