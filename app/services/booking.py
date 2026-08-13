"""BookingService - 조회/좌석/예약/취소 오케스트레이션.

라우터는 이 서비스만 호출한다. 서비스는 provider 팩토리와 credential store 를 묶어
"어떤 계정으로 어떤 provider 를 쓸지"를 결정한다.
"""

from __future__ import annotations

from functools import lru_cache

from app.credentials import get_credential_store
from app.providers import get_provider
from app.schemas import (
    CarSeats,
    Passengers,
    Reservation,
    SeatClass,
    TrainOption,
    TrainType,
)


class BookingService:
    def __init__(self) -> None:
        self._credentials = get_credential_store()

    def _cred(self, train_type: TrainType, label: str | None):
        return self._credentials.get(train_type, label)

    # ---------------------------------------------------------------- search
    def search(
        self,
        train_type: TrainType,
        dep: str,
        arr: str,
        date: str,
        time: str,
        *,
        passengers: Passengers,
        credential_label: str | None = None,
        limit: int = 10,
        include_no_seats: bool = True,
    ) -> list[TrainOption]:
        cred = self._cred(train_type, credential_label)
        provider = get_provider(train_type)
        return provider.search(
            cred, dep, arr, date, time,
            passengers=passengers,
            limit=limit,
            include_no_seats=include_no_seats,
        )

    # ----------------------------------------------------------------- seats
    def seats(
        self,
        train: TrainOption,
        *,
        credential_label: str | None = None,
        seat_class: SeatClass | None = None,
        car_no: int | None = None,
        available_only: bool = False,
    ) -> list[CarSeats]:
        cred = self._cred(train.train_type, credential_label)
        provider = get_provider(train.train_type)
        return provider.seats(
            cred, train,
            seat_class=seat_class,
            car_no=car_no,
            available_only=available_only,
        )

    # --------------------------------------------------------------- reserve
    def reserve(
        self,
        train: TrainOption,
        *,
        passengers: Passengers,
        seat_class: SeatClass = SeatClass.GENERAL,
        credential_label: str | None = None,
    ) -> Reservation:
        cred = self._cred(train.train_type, credential_label)
        provider = get_provider(train.train_type)
        return provider.reserve(cred, train, passengers=passengers, seat_class=seat_class)

    # ---------------------------------------------------- list_reservations
    def list_reservations(
        self, train_type: TrainType, *, credential_label: str | None = None
    ) -> list[Reservation]:
        cred = self._cred(train_type, credential_label)
        provider = get_provider(train_type)
        return provider.list_reservations(cred)

    def all_reservations(self) -> list[Reservation]:
        """등록된 모든 계정의 예약을 모아서 반환."""
        result: list[Reservation] = []
        for cred in self._credentials.list_credentials():
            provider = get_provider(cred.provider)
            result.extend(provider.list_reservations(cred))
        return result

    # ---------------------------------------------------------------- cancel
    def cancel(
        self, train_type: TrainType, reservation_id: str, *, credential_label: str | None = None
    ) -> Reservation:
        cred = self._cred(train_type, credential_label)
        provider = get_provider(train_type)
        return provider.cancel(cred, reservation_id)


@lru_cache
def get_booking_service() -> BookingService:
    return BookingService()
