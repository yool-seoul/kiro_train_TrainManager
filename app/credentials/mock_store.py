"""Mock 자격증명 저장소.

실제 계정 없이 UI/흐름을 시연하기 위한 가짜 계정을 제공한다.
Mock provider 는 자격증명 내용을 실제로 검증하지 않는다.
"""

from __future__ import annotations

from app.credentials.base import CredentialStore
from app.schemas import Credential, TrainType


class MockCredentialStore(CredentialStore):
    def __init__(self) -> None:
        self._creds = [
            Credential(
                provider=TrainType.KTX,
                login_id="ktx_demo_user",
                password="mock",
                label="데모 KTX 계정",
            ),
            Credential(
                provider=TrainType.SRT,
                login_id="srt_demo_user",
                password="mock",
                label="데모 SRT 계정",
            ),
        ]

    def list_credentials(self, train_type: TrainType | None = None) -> list[Credential]:
        if train_type is None:
            return list(self._creds)
        return [c for c in self._creds if c.provider is train_type]
