"""CredentialStore 추상 인터페이스."""

from __future__ import annotations

import abc

from app.schemas import Credential, TrainType


class CredentialError(Exception):
    """자격증명 로드 오류."""


class CredentialStore(abc.ABC):
    """열차 예매 계정 자격증명 소스.

    구현체는 여러 계정을 label 로 구분해 제공한다.
    """

    @abc.abstractmethod
    def list_credentials(self, train_type: TrainType | None = None) -> list[Credential]:
        """계정 목록. train_type 지정 시 해당 provider 계정만."""

    def get(self, train_type: TrainType, label: str | None = None) -> Credential:
        """train_type + label 로 단일 계정 선택.

        label 이 없으면 해당 provider 의 첫 계정을 사용한다.
        """
        candidates = self.list_credentials(train_type)
        if not candidates:
            raise CredentialError(f"{train_type.value} 계정이 없습니다.")
        if label is None:
            return candidates[0]
        for cred in candidates:
            if cred.label == label:
                return cred
        raise CredentialError(f"계정을 찾을 수 없습니다: {train_type.value}/{label}")
