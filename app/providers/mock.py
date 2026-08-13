"""Mock provider - 가짜 데이터로 전체 흐름을 구동한다.

실제 Korail/SRT 에 접속하지 않으므로 계정/네트워크 없이 UI·로직·리뷰가 가능하다.
자동 예약대기(watch) 를 시연할 수 있도록, 매진 열차가 폴링 중 확률적으로
좌석이 풀리도록 설계했다.
"""

from __future__ import annotations

import hashlib
import random
import threading
from datetime import datetime, timedelta

from app.providers.base import ProviderError, TrainProvider
from app.schemas import (
    CarSeats,
    Credential,
    Passengers,
    Reservation,
    ReservationStatus,
    SeatClass,
    SeatDetail,
    TrainOption,
    TrainType,
)

# 매진 열차가 폴링 1회마다 좌석이 풀릴 확률 (watch 시연용)
_SEAT_RELEASE_PROBABILITY = 0.35


def _seed(*parts: str) -> int:
    """문자열들로부터 안정적인 정수 시드 생성."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest[:8], 16)


class MockProvider(TrainProvider):
    """열차사별로 인스턴스를 만든다 (train_type 만 다름)."""

    def __init__(self, train_type: TrainType) -> None:
        self.train_type = train_type
        # login_id -> 예약 목록 (프로세스 메모리, 재시작 시 초기화)
        self._reservations: dict[str, list[Reservation]] = {}
        self._lock = threading.Lock()
        self._counter = 0

    # ----------------------------------------------------------------- search
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
        try:
            base = datetime.strptime(date + time, "%Y%m%d%H%M%S")
        except ValueError as exc:
            raise ProviderError(f"잘못된 날짜/시각 형식: {date} {time}", code="bad_input") from exc

        rng = random.Random(_seed(self.train_type.value, dep, arr, date))
        prefix = "KTX" if self.train_type is TrainType.KTX else "SRT"

        options: list[TrainOption] = []
        n = min(limit, 8) if limit else 8
        for i in range(max(n, 1)):
            dep_time = base + timedelta(minutes=45 * i + rng.randint(0, 20))
            duration = timedelta(hours=2, minutes=rng.randint(30, 55))
            train_no = 100 + rng.randint(0, 400) + i
            train_id = f"{self.train_type.value}-{date}-{dep}-{arr}-{dep_time.strftime('%H%M')}"

            # 약 40% 는 매진 상태로 시작 (watch 시연용)
            general_avail = rng.random() > 0.4
            special_avail = rng.random() > 0.6
            # 매진 열차라도 폴링 중 확률적으로 좌석이 풀린다
            if not general_avail and rng.random() < _SEAT_RELEASE_PROBABILITY:
                general_avail = True

            general_fare = 20000 + rng.randint(0, 40) * 500
            options.append(
                TrainOption(
                    train_id=train_id,
                    train_type=self.train_type,
                    train_name=f"{prefix} {train_no}",
                    dep_station=dep,
                    arr_station=arr,
                    dep_time=dep_time,
                    arr_time=dep_time + duration,
                    general_available=general_avail,
                    special_available=special_avail,
                    waiting_available=not general_avail,
                    general_fare=general_fare,
                    special_fare=int(general_fare * 1.4),
                )
            )

        if not include_no_seats:
            options = [o for o in options if o.any_available]
        return options

    # ------------------------------------------------------------------ seats
    def seats(
        self,
        credential: Credential,
        train: TrainOption,
        *,
        seat_class: SeatClass | None = None,
        car_no: int | None = None,
        available_only: bool = False,
    ) -> list[CarSeats]:
        rng = random.Random(_seed(train.train_id, "seats"))
        total_cars = 8
        cars: list[CarSeats] = []
        for c in range(1, total_cars + 1):
            cls = SeatClass.SPECIAL if c <= 2 else SeatClass.GENERAL
            if seat_class and cls is not seat_class:
                continue
            if car_no and c != car_no:
                continue

            seats: list[SeatDetail] = []
            rows = 15 if cls is SeatClass.GENERAL else 10
            cols = ["A", "B", "C", "D"] if cls is SeatClass.GENERAL else ["A", "B"]
            for row in range(1, rows + 1):
                for col in cols:
                    avail = rng.random() > 0.75
                    if available_only and not avail:
                        continue
                    seats.append(
                        SeatDetail(
                            seat_no=f"{row}{col}",
                            seat_class=cls,
                            is_available=avail,
                            direction="forward" if row % 2 else "backward",
                            position="window" if col in ("A", "D") else "aisle",
                            power_outlet="direct" if col in ("A", "D") else "none",
                            near_door=row in (1, rows),
                        )
                    )
            cars.append(
                CarSeats(
                    car_no=c,
                    seat_class=cls,
                    available_seat_count=sum(1 for s in seats if s.is_available),
                    seats=seats,
                )
            )
        return cars

    # ---------------------------------------------------------------- reserve
    def reserve(
        self,
        credential: Credential,
        train: TrainOption,
        *,
        passengers: Passengers,
        seat_class: SeatClass = SeatClass.GENERAL,
    ) -> Reservation:
        available = (
            train.general_available
            if seat_class is SeatClass.GENERAL
            else train.special_available
        )
        if not available:
            raise ProviderError("해당 좌석 등급은 매진입니다.", code="sold_out")

        rng = random.Random(_seed(train.train_id, seat_class.value, credential.login_id))
        with self._lock:
            self._counter += 1
            res_no = f"{self.train_type.value.upper()}{datetime.now():%y%m%d}{self._counter:04d}"

        fare_each = (
            train.general_fare if seat_class is SeatClass.GENERAL else train.special_fare
        ) or 0
        car = rng.randint(3, 8) if seat_class is SeatClass.GENERAL else rng.randint(1, 2)
        seat_no = f"{car}호차 {rng.randint(1, 15)}{rng.choice(['A', 'B', 'C', 'D'])}"

        reservation = Reservation(
            reservation_id=res_no,
            train_type=self.train_type,
            train_name=train.train_name,
            dep_station=train.dep_station,
            arr_station=train.arr_station,
            dep_time=train.dep_time,
            arr_time=train.arr_time,
            seat_class=seat_class,
            seat_no=seat_no,
            passengers=passengers,
            fare=fare_each * max(passengers.total, 1),
            status=ReservationStatus.RESERVED,
            deadline=datetime.now() + timedelta(minutes=10),
        )
        with self._lock:
            self._reservations.setdefault(credential.login_id, []).append(reservation)
        return reservation

    # ------------------------------------------------------ list_reservations
    def list_reservations(self, credential: Credential) -> list[Reservation]:
        with self._lock:
            return list(self._reservations.get(credential.login_id, []))

    # ----------------------------------------------------------------- cancel
    def cancel(self, credential: Credential, reservation_id: str) -> Reservation:
        with self._lock:
            items = self._reservations.get(credential.login_id, [])
            for res in items:
                if res.reservation_id == reservation_id:
                    if res.status is ReservationStatus.CANCELLED:
                        raise ProviderError("이미 취소된 예약입니다.", code="already_cancelled")
                    res.status = ReservationStatus.CANCELLED
                    return res
        raise ProviderError(f"예약을 찾을 수 없습니다: {reservation_id}", code="not_found")
