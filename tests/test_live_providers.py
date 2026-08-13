"""실연동 provider(KTX/SRT) 매핑 단위 테스트.

실제 Korail/SRT 에 접속하지 않는다. 가짜 `korail2`/`SRT` 모듈을 sys.modules 에 주입하고,
provider 의 client 캐시에 가짜 client 를 직접 넣어 매핑 로직만 검증한다.
(실제 예약/취소는 절대 실행되지 않는다.)
"""

from __future__ import annotations

import sys
import types

import pytest

from app.schemas import Passengers, ReservationStatus, SeatClass, TrainType


# --------------------------------------------------------------------- KTX fakes
class FakeKorailTrain:
    def __init__(self, general=True, special=False, waiting=False):
        self.run_date = "20260901"
        self.train_no = "101"
        self.dep_code = "0001"
        self.arr_code = "0020"
        self.train_type_name = "KTX"
        self.dep_name = "서울"
        self.arr_name = "부산"
        self.dep_date = "20260901"
        self.dep_time = "090000"
        self.arr_date = "20260901"
        self.arr_time = "114300"
        self._g, self._s, self._w = general, special, waiting

    def has_general_seat(self):
        return self._g

    def has_special_seat(self):
        return self._s

    def has_general_waiting_list(self):
        return self._w


class FakeKorailReservation:
    def __init__(self):
        self.rsv_id = "KTX20260901001"
        self.train_type_name = "KTX"
        self.train_no = "101"
        self.dep_name = "서울"
        self.arr_name = "부산"
        self.dep_date = "20260901"
        self.dep_time = "090000"
        self.arr_date = "20260901"
        self.arr_time = "114300"
        self.price = 59800
        self.seat_no_count = 1
        self.buy_limit_date = "20260901"
        self.buy_limit_time = "093000"


class FakeKorailClient:
    def __init__(self):
        self.logined = True
        self.reserved = None

    def search_train(self, *a, **k):
        return [FakeKorailTrain(general=True, special=True)]

    def reserve(self, train, passengers=None, option=None):
        self.reserved = FakeKorailReservation()
        return self.reserved

    def reservations(self):
        return [FakeKorailReservation()]

    def cancel(self, obj):
        return True


@pytest.fixture
def fake_korail(monkeypatch):
    mod = types.ModuleType("korail2")

    class NoResultsError(Exception):
        pass

    class SoldOutError(Exception):
        pass

    class TrainType_:
        KTX = "100"

    class ReserveOption:
        GENERAL_FIRST = "GENERAL_FIRST"
        SPECIAL_FIRST = "SPECIAL_FIRST"

    def _p(cls_name):
        return type(cls_name, (), {"__init__": lambda self, count=1: setattr(self, "count", count)})

    mod.Korail = object
    mod.NoResultsError = NoResultsError
    mod.SoldOutError = SoldOutError
    mod.TrainType = TrainType_
    mod.ReserveOption = ReserveOption
    mod.AdultPassenger = _p("AdultPassenger")
    mod.ChildPassenger = _p("ChildPassenger")
    mod.SeniorPassenger = _p("SeniorPassenger")
    monkeypatch.setitem(sys.modules, "korail2", mod)
    return mod


def test_ktx_search_and_reserve_mapping(fake_korail):
    from app.providers.ktx import KtxProvider
    from app.schemas import Credential

    provider = KtxProvider()
    cred = Credential(provider=TrainType.KTX, login_id="ktxid", password="pw")
    # 가짜 client 주입 (로그인/네트워크 우회)
    provider._clients._clients["ktxid"] = FakeKorailClient()

    trains = provider.search(cred, "서울", "부산", "20260901", "090000", passengers=Passengers(adults=1))
    assert len(trains) == 1
    t = trains[0]
    assert t.train_type is TrainType.KTX
    assert t.train_id.startswith("ktx-20260901-101-")
    assert t.general_available and t.special_available

    # 예약 매핑 (가짜 reserve → 실제 예약 아님)
    res = provider.reserve(cred, t, passengers=Passengers(adults=1), seat_class=SeatClass.GENERAL)
    assert res.reservation_id == "KTX20260901001"
    assert res.fare == 59800
    assert res.status is ReservationStatus.RESERVED
    assert res.deadline is not None


def test_ktx_cancel_sets_cancelled(fake_korail):
    from app.providers.ktx import KtxProvider
    from app.schemas import Credential

    provider = KtxProvider()
    cred = Credential(provider=TrainType.KTX, login_id="ktxid", password="pw")
    provider._clients._clients["ktxid"] = FakeKorailClient()

    res = provider.cancel(cred, "KTX20260901001")
    assert res.status is ReservationStatus.CANCELLED


def test_ktx_seats_not_supported(fake_korail):
    from app.providers.ktx import KtxProvider
    from app.providers.base import ProviderError
    from app.schemas import Credential, TrainOption
    from datetime import datetime

    provider = KtxProvider()
    cred = Credential(provider=TrainType.KTX, login_id="ktxid", password="pw")
    provider._clients._clients["ktxid"] = FakeKorailClient()
    dummy = TrainOption(
        train_id="ktx-x", train_type=TrainType.KTX, train_name="KTX 1",
        dep_station="서울", arr_station="부산",
        dep_time=datetime.now(), arr_time=datetime.now(),
    )
    with pytest.raises(ProviderError) as exc:
        provider.seats(cred, dummy)
    assert exc.value.code == "not_supported"


# --------------------------------------------------------------------- SRT fakes
class FakeSRTTrain:
    def __init__(self, general=True, special=False):
        self.train_name = "SRT"
        self.train_code = "17"
        self.train_number = "351"
        self.dep_date = "20260901"
        self.dep_time = "080000"
        self.dep_station_code = "0551"
        self.dep_station_name = "수서"
        self.arr_date = "20260901"
        self.arr_time = "102400"
        self.arr_station_code = "0020"
        self.arr_station_name = "부산"
        self._g, self._s = general, special

    def general_seat_available(self):
        return self._g

    def special_seat_available(self):
        return self._s

    def reserve_standby_available(self):
        return False


class FakeSRTTicket:
    def __init__(self):
        self.car = "3"
        self.seat = "10A"


class FakeSRTReservation:
    def __init__(self):
        self.reservation_number = "SRT99887766"
        self.total_cost = 53700
        self.seat_count = 1
        self.train_name = "SRT"
        self.dep_date = "20260901"
        self.dep_time = "080000"
        self.dep_station_name = "수서"
        self.arr_date = "20260901"
        self.arr_time = "102400"
        self.arr_station_name = "부산"
        self.payment_date = "20260901"
        self.payment_time = "083000"
        self.paid = False
        self.tickets = [FakeSRTTicket()]


class FakeSRTClient:
    def __init__(self):
        self.is_login = True

    def search_train(self, *a, **k):
        return [FakeSRTTrain(general=True, special=True)]

    def reserve(self, train, passengers=None, special_seat=None):
        return FakeSRTReservation()

    def get_reservations(self):
        return [FakeSRTReservation()]

    def cancel(self, obj):
        return True


@pytest.fixture
def fake_srt(monkeypatch):
    mod = types.ModuleType("SRT")
    passenger_mod = types.ModuleType("SRT.passenger")

    def _p(cls_name):
        return type(cls_name, (), {"__init__": lambda self, count=1: setattr(self, "count", count)})

    passenger_mod.Adult = _p("Adult")
    passenger_mod.Child = _p("Child")
    passenger_mod.Senior = _p("Senior")

    class SeatType:
        GENERAL_FIRST = "GENERAL_FIRST"
        SPECIAL_FIRST = "SPECIAL_FIRST"

    mod.SRT = object
    mod.SeatType = SeatType
    mod.passenger = passenger_mod
    monkeypatch.setitem(sys.modules, "SRT", mod)
    monkeypatch.setitem(sys.modules, "SRT.passenger", passenger_mod)
    return mod


def test_srt_search_and_reserve_mapping(fake_srt):
    from app.providers.srt import SrtProvider
    from app.schemas import Credential

    provider = SrtProvider()
    cred = Credential(provider=TrainType.SRT, login_id="srtid", password="pw")
    provider._clients._clients["srtid"] = FakeSRTClient()

    trains = provider.search(cred, "수서", "부산", "20260901", "080000", passengers=Passengers(adults=1))
    assert len(trains) == 1
    t = trains[0]
    assert t.train_type is TrainType.SRT
    assert t.train_id.startswith("srt-20260901-351-")

    res = provider.reserve(cred, t, passengers=Passengers(adults=1), seat_class=SeatClass.GENERAL)
    assert res.reservation_id == "SRT99887766"
    assert res.fare == 53700
    assert res.seat_no == "3호차 10A"
    assert res.status is ReservationStatus.RESERVED
    assert res.deadline is not None


def test_srt_cancel_sets_cancelled(fake_srt):
    from app.providers.srt import SrtProvider
    from app.schemas import Credential

    provider = SrtProvider()
    cred = Credential(provider=TrainType.SRT, login_id="srtid", password="pw")
    provider._clients._clients["srtid"] = FakeSRTClient()

    res = provider.cancel(cred, "SRT99887766")
    assert res.status is ReservationStatus.CANCELLED
