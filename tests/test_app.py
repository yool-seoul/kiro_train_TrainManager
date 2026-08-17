"""기본 스모크/단위 테스트 (Mock 모드).

실행: pytest
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Passengers, SeatClass, TrainType
from app.services import get_booking_service, get_watch_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def _force_mock(monkeypatch):
    """이 모듈의 통합 스모크 테스트는 mock provider 기준이다.

    실제 .env 가 data_source=live 여도 여기서는 mock 으로 고정해
    외부(Korail/SRT) 의존 없이 결정적으로 동작하게 한다.
    """
    from app.config import get_settings
    from app.providers.factory import reset_providers

    settings = get_settings()
    monkeypatch.setattr(settings, "data_source", "mock")
    monkeypatch.setattr(settings, "notify_channel", "none")
    reset_providers()
    yield
    reset_providers()


def test_index_page():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "열차 좌석 조회" in resp.text


def test_search_returns_results():
    resp = client.post(
        "/search",
        data={
            "train_type": "ktx",
            "dep": "서울",
            "arr": "부산",
            "date": "2026-09-01",
            "time": "09:00",
            "seat_class": "general",
            "adults": 1,
        },
    )
    assert resp.status_code == 200
    assert "조회 결과" in resp.text


def test_booking_search_and_reserve():
    booking = get_booking_service()
    trains = booking.search(
        TrainType.KTX, "서울", "부산", "20260901", "090000",
        passengers=Passengers(adults=1),
    )
    assert trains, "mock 은 항상 일부 열차를 반환해야 한다"

    available = [t for t in trains if t.general_available]
    assert available, "일반실 가능한 열차가 최소 하나는 있어야 한다"

    res = booking.reserve(available[0], passengers=Passengers(adults=1))
    assert res.reservation_id
    assert res.status.value == "reserved"

    # 예약 목록/취소
    listed = booking.list_reservations(TrainType.KTX)
    assert any(r.reservation_id == res.reservation_id for r in listed)

    cancelled = booking.cancel(TrainType.KTX, res.reservation_id)
    assert cancelled.status.value == "cancelled"


def test_watch_job_eventually_reserves(monkeypatch):
    """폴링 주기를 짧게 바꿔 watch 가 좌석을 선점하는지 확인."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "watch_min_interval_sec", 0)
    monkeypatch.setattr(settings, "watch_poll_interval_sec", 0)

    watch = get_watch_service()
    job = watch.create_watch(
        TrainType.SRT, "수서", "부산", "20260901", "080000",
        passengers=Passengers(adults=1),
        seat_class=SeatClass.GENERAL,
    )

    # 최대 3초 대기하며 상태 변화를 관찰 (mock 은 곧 좌석을 선점해야 함)
    for _ in range(30):
        current = watch.get(job.job_id)
        if current and current.status.value == "reserved":
            break
        time.sleep(0.1)

    current = watch.get(job.job_id)
    assert current is not None
    assert current.status.value in {"reserved", "watching"}
    watch.stop(job.job_id)


def test_target_train_watch_reserves_that_train(monkeypatch):
    """특정 열차를 지정한 대기가 그 열차를 선점하는지 확인."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "watch_min_interval_sec", 0)
    monkeypatch.setattr(settings, "watch_poll_interval_sec", 0)

    booking = get_booking_service()
    # 매진(전 좌석 불가) 열차를 하나 찾는다. mock 은 곧 좌석을 푼다.
    trains = booking.search(
        TrainType.KTX, "서울", "동대구", "20261115", "070000",
        passengers=Passengers(adults=1), include_no_seats=True,
    )
    target = trains[0]

    watch = get_watch_service()
    job = watch.create_watch(
        TrainType.KTX, "서울", "동대구", "20261115", "070000",
        passengers=Passengers(adults=1),
        seat_class=SeatClass.GENERAL,
        target_train_id=target.train_id,
        target_train_name=target.train_name,
    )
    assert job.target_train_id == target.train_id
    watch.stop(job.job_id)


def test_reserved_watch_cannot_be_stopped(monkeypatch):
    """예약 완료된 대기 작업은 중단(취소)되지 않고 상태가 유지되어야 한다."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "watch_min_interval_sec", 0)
    monkeypatch.setattr(settings, "watch_poll_interval_sec", 0)

    watch = get_watch_service()
    job = watch.create_watch(
        TrainType.SRT, "수서", "부산", "20260901", "080000",
        passengers=Passengers(adults=1),
    )
    # reserved 될 때까지 대기
    for _ in range(50):
        cur = watch.get(job.job_id)
        if cur and cur.status.value == "reserved":
            break
        time.sleep(0.1)

    cur = watch.get(job.job_id)
    assert cur is not None and cur.status.value == "reserved"
    assert cur.is_active is False
    assert "end waiting" in cur.status_label

    # 중단 시도 → 상태가 바뀌지 않아야 함
    result = watch.stop(job.job_id)
    assert result is not None and result.status.value == "reserved"
