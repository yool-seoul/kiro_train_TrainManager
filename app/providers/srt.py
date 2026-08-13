"""SRT provider (실연동).

`SRTrain` (import 이름 `SRT`) 를 감싼다. `data_source=live` 일 때 사용된다.

참고(k-skill/srt-booking):
- 상세 좌석맵은 기본 API 가 제공하지 않아 live 에서는 미지원.
"""

from __future__ import annotations

from datetime import datetime

from app.providers._live import ClientCache, RawTrainCache, parse_dt
from app.providers.base import ProviderError, TrainProvider
from app.schemas import (
    CarSeats,
    Credential,
    Passengers,
    Reservation,
    ReservationStatus,
    SeatClass,
    TrainOption,
    TrainType,
)


def _make_srt(login_id: str, password: str):
    """로그인된 SRT client 생성. (테스트에서 monkeypatch 가능)"""
    try:
        from SRT import SRT  # type: ignore
    except ImportError as exc:
        raise ProviderError(
            "SRTrain 미설치. `pip install SRTrain` 후 사용.",
            code="dependency_missing",
        ) from exc
    try:
        client = SRT(login_id, password, auto_login=True)
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(f"SRT 로그인 오류: {exc}", code="login_error") from exc
    if not getattr(client, "is_login", False):
        raise ProviderError("SRT 로그인 실패: 계정/비밀번호를 확인하세요.", code="login_failed")
    return client


class SrtProvider(TrainProvider):
    train_type = TrainType.SRT

    def __init__(self) -> None:
        self._clients: ClientCache = ClientCache(_make_srt)
        self._raw = RawTrainCache()

    # ------------------------------------------------------------- helpers
    def _client(self, credential: Credential):
        return self._clients.get(credential.login_id, credential.password)

    @staticmethod
    def _train_id(t) -> str:
        return f"srt-{t.dep_date}-{t.train_number}-{t.dep_station_code}-{t.arr_station_code}-{t.dep_time[:4]}"

    def _to_option(self, t) -> TrainOption:
        return TrainOption(
            train_id=self._train_id(t),
            train_type=TrainType.SRT,
            train_name=f"SRT {t.train_number}",
            dep_station=t.dep_station_name,
            arr_station=t.arr_station_name,
            dep_time=parse_dt(t.dep_date, t.dep_time),
            arr_time=parse_dt(getattr(t, "arr_date", t.dep_date), t.arr_time),
            general_available=t.general_seat_available(),
            special_available=t.special_seat_available(),
            waiting_available=t.reserve_standby_available(),
            general_fare=None,   # SRT search 는 운임 미제공
            special_fare=None,
        )

    def _passengers(self, p: Passengers) -> list:
        from SRT import passenger as srt_passenger  # type: ignore

        out = []
        adult_cls = getattr(srt_passenger, "Adult", None)
        child_cls = getattr(srt_passenger, "Child", None)
        senior_cls = getattr(srt_passenger, "Senior", None)
        if p.adults and adult_cls:
            out.append(adult_cls(p.adults))
        if p.children and child_cls:
            out.append(child_cls(p.children))
        if p.seniors and senior_cls:
            out.append(senior_cls(p.seniors))
        if not out and adult_cls:
            out.append(adult_cls(1))
        return out

    # -------------------------------------------------------------- search
    def search(self, credential, dep, arr, date, time, *, passengers, limit=10, include_no_seats=True) -> list[TrainOption]:
        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)
        with lock:
            try:
                trains = client.search_train(
                    dep, arr, date, time,
                    available_only=not include_no_seats,
                )
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"SRT 조회 오류: {exc}", code="search_error") from exc

        options = []
        for t in trains[: limit or len(trains)]:
            self._raw.put(self._train_id(t), t)
            options.append(self._to_option(t))
        return options

    # --------------------------------------------------------------- seats
    def seats(self, credential, train, *, seat_class=None, car_no=None, available_only=False) -> list[CarSeats]:
        raise ProviderError(
            "실연동(SRT) 모드에서는 상세 좌석 조회를 아직 지원하지 않습니다. "
            "일반실/특실 예약 가능 여부는 조회 목록을 참고하세요.",
            code="not_supported",
        )

    # ------------------------------------------------------------- reserve
    def reserve(self, credential, train, *, passengers, seat_class=SeatClass.GENERAL) -> Reservation:
        from SRT import SeatType  # type: ignore

        raw = self._raw.get(train.train_id)
        if raw is None:
            raise ProviderError(
                "예약 대상 열차 정보가 만료되었습니다. 다시 조회 후 예약하세요.",
                code="stale_train",
            )
        special = (
            SeatType.SPECIAL_FIRST
            if seat_class is SeatClass.SPECIAL
            else SeatType.GENERAL_FIRST
        )
        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)
        with lock:
            try:
                rsv = client.reserve(
                    raw, passengers=self._passengers(passengers), special_seat=special
                )
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"SRT 예약 오류: {exc}", code="reserve_error") from exc
        return self._reservation_to_model(rsv, seat_class, passengers)

    # -------------------------------------------------- list_reservations
    def list_reservations(self, credential) -> list[Reservation]:
        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)
        with lock:
            try:
                items = client.get_reservations()
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"SRT 예약 목록 오류: {exc}", code="list_error") from exc
        return [self._reservation_to_model(r) for r in items]

    # -------------------------------------------------------------- cancel
    def cancel(self, credential, reservation_id) -> Reservation:
        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)
        with lock:
            try:
                items = client.get_reservations()
                target = next(
                    (r for r in items if str(r.reservation_number) == str(reservation_id)),
                    None,
                )
                if target is None:
                    raise ProviderError(f"예약을 찾을 수 없습니다: {reservation_id}", code="not_found")
                client.cancel(target)
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"SRT 취소 오류: {exc}", code="cancel_error") from exc
        model = self._reservation_to_model(target)
        model.status = ReservationStatus.CANCELLED
        return model

    # ------------------------------------------------------------- mapping
    def _reservation_to_model(
        self, r, seat_class: SeatClass = SeatClass.GENERAL, passengers: Passengers | None = None
    ) -> Reservation:
        deadline = None
        pay_date = getattr(r, "payment_date", None)
        pay_time = getattr(r, "payment_time", None)
        if pay_date and pay_time and not getattr(r, "paid", False):
            deadline = parse_dt(pay_date, pay_time)

        seat_no = None
        tickets = getattr(r, "tickets", None) or []
        if tickets:
            first = tickets[0]
            seat_no = f"{getattr(first, 'car', '')}호차 {getattr(first, 'seat', '')}".strip()

        count = int(getattr(r, "seat_count", 0) or (passengers.total if passengers else 1))
        status = ReservationStatus.PAID if getattr(r, "paid", False) else ReservationStatus.RESERVED
        return Reservation(
            reservation_id=str(r.reservation_number),
            train_type=TrainType.SRT,
            train_name=getattr(r, "train_name", "SRT"),
            dep_station=r.dep_station_name,
            arr_station=r.arr_station_name,
            dep_time=parse_dt(r.dep_date, r.dep_time),
            arr_time=parse_dt(getattr(r, "arr_date", r.dep_date), r.arr_time),
            seat_class=seat_class,
            seat_no=seat_no,
            passengers=passengers or Passengers(adults=max(count, 1)),
            fare=int(getattr(r, "total_cost", 0) or 0),
            status=status,
            deadline=deadline,
            created_at=datetime.now(),
        )
