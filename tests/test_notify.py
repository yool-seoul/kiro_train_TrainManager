"""알림(메신저) 단위 테스트. 실제 전송은 하지 않는다."""

from __future__ import annotations

from datetime import datetime

from app.notify.base import (
    Notifier,
    build_reservation_message,
    build_reserved_message,
)
from app.schemas import (
    Passengers,
    Reservation,
    ReservationStatus,
    SeatClass,
    TrainType,
    WatchJob,
    WatchStatus,
)


def _reservation() -> Reservation:
    return Reservation(
        reservation_id="KTX20260901001",
        train_type=TrainType.KTX,
        train_name="KTX 101",
        dep_station="서울",
        arr_station="부산",
        dep_time=datetime(2026, 9, 1, 9, 0),
        arr_time=datetime(2026, 9, 1, 11, 43),
        seat_class=SeatClass.SPECIAL,
        seat_no="3호차 5A~6A",
        passengers=Passengers(adults=2),
        fare=119600,
        status=ReservationStatus.RESERVED,
        deadline=datetime(2026, 9, 1, 9, 30),
    )


def _reserved_job() -> WatchJob:
    res = Reservation(
        reservation_id="SRT123",
        train_type=TrainType.SRT,
        train_name="SRT 351",
        dep_station="수서",
        arr_station="부산",
        dep_time=datetime(2026, 9, 1, 8, 0),
        arr_time=datetime(2026, 9, 1, 10, 24),
        seat_class=SeatClass.GENERAL,
        seat_no="3호차 10A",
        passengers=Passengers(adults=1),
        fare=53700,
        status=ReservationStatus.RESERVED,
        deadline=datetime(2026, 9, 1, 8, 30),
    )
    return WatchJob(
        job_id="j1", train_type=TrainType.SRT, dep_station="수서", arr_station="부산",
        date="20260901", time="080000", passengers=Passengers(adults=1),
        status=WatchStatus.RESERVED, reservation=res,
    )


def test_build_reserved_message_contains_key_fields():
    msg = build_reserved_message(_reserved_job())
    assert "좌석 선점 완료" in msg
    assert "SRT 351" in msg
    assert "SRT123" in msg
    assert "53,700원" in msg
    assert "3호차 10A" in msg


def test_build_reservation_message_contains_key_fields():
    msg = build_reservation_message(_reservation())
    assert "좌석 선점 완료" in msg
    assert "KTX 101" in msg
    assert "KTX20260901001" in msg
    assert "특실" in msg
    assert "3호차 5A~6A" in msg
    assert "119,600원" in msg
    assert "2명" in msg


def test_notifier_notify_reservation_calls_send():
    sent = []

    class FakeNotifier(Notifier):
        def send(self, text: str) -> None:
            sent.append(text)

    FakeNotifier().notify_reservation(_reservation())
    assert len(sent) == 1
    assert "KTX 101" in sent[0]


def test_notifier_notify_reserved_calls_send():
    sent = []

    class FakeNotifier(Notifier):
        def send(self, text: str) -> None:
            sent.append(text)

    FakeNotifier().notify_reserved(_reserved_job())
    assert len(sent) == 1
    assert "좌석 선점 완료" in sent[0]


def test_factory_defaults_to_null(monkeypatch):
    from app.config import get_settings
    from app.notify.factory import get_notifier, reset_notifier
    from app.notify.channels import NullNotifier

    reset_notifier()
    s = get_settings()
    monkeypatch.setattr(s, "notify_channel", "none")
    assert isinstance(get_notifier(), NullNotifier)
    reset_notifier()
