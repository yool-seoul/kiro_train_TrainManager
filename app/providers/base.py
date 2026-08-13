"""TrainProvider 추상 인터페이스.

KTX(Korail)와 SRT 의 차이를 이 인터페이스 뒤로 감춘다.
서비스/라우터 레이어는 provider 의 구체 타입을 몰라도 된다.
"""

from __future__ import annotations

import abc

from app.schemas import (
    CarSeats,
    Credential,
    Passengers,
    Reservation,
    SeatClass,
    TrainOption,
    TrainType,
)


class ProviderError(Exception):
    """provider 계층에서 발생하는 도메인 오류 (로그인 실패, 매진, 예약 실패 등)."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TrainProvider(abc.ABC):
    """열차 조회/예약/취소 provider.

    구현체는 stateless 하게 유지하고, 자격증명은 메서드 인자로 받는다.
    (세션/요청 단위로 다른 계정을 쓸 수 있어야 하므로)
    """

    train_type: TrainType

    @abc.abstractmethod
    def search(
        self,
        credential: Credential,
        dep: str,
        arr: str,
        date: str,
        time: str,
        *,
        passengers: Passengers,
        limit: int = 10,
        include_no_seats: bool = True,
    ) -> list[TrainOption]:
        """열차 목록 조회.

        Args:
            date: YYYYMMDD
            time: HHMMSS (희망 시작 시각)
        """

    @abc.abstractmethod
    def seats(
        self,
        credential: Credential,
        train: TrainOption,
        *,
        seat_class: SeatClass | None = None,
        car_no: int | None = None,
        available_only: bool = False,
    ) -> list[CarSeats]:
        """특정 열차의 호차별 좌석 상세 조회 (읽기 전용)."""

    @abc.abstractmethod
    def reserve(
        self,
        credential: Credential,
        train: TrainOption,
        *,
        passengers: Passengers,
        seat_class: SeatClass = SeatClass.GENERAL,
    ) -> Reservation:
        """좌석 선점(예약). 결제는 별도(handoff)."""

    @abc.abstractmethod
    def list_reservations(self, credential: Credential) -> list[Reservation]:
        """현재 예약 목록 조회."""

    @abc.abstractmethod
    def cancel(self, credential: Credential, reservation_id: str) -> Reservation:
        """예약 취소."""
