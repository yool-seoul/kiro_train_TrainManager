"""KTX/Korail provider (실연동).

`korail2-ncard` (import 이름 `korail2`) 를 감싼다. `data_source=live` 일 때 사용된다.

참고(k-skill/ktx-booking):
- 원본 korail2 는 anti-bot(Dynapath) 때문에 MACRO ERROR 가능 → korail2-ncard 사용.
- 상세 좌석맵(호차별 좌석번호)은 korail2 기본 API 가 제공하지 않아 live 에서는 미지원.
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


def _make_korail(login_id: str, password: str):
    """로그인된 Korail client 생성. (테스트에서 monkeypatch 가능)"""
    try:
        from korail2 import Korail  # type: ignore
    except ImportError as exc:
        raise ProviderError(
            "korail2-ncard 미설치. `pip install korail2-ncard pycryptodome` 후 사용.",
            code="dependency_missing",
        ) from exc
    try:
        client = Korail(login_id, password, auto_login=True)
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(f"KTX 로그인 오류: {exc}", code="login_error") from exc
    if not getattr(client, "logined", False):
        raise ProviderError("KTX 로그인 실패: 계정/비밀번호를 확인하세요.", code="login_failed")
    return client


class KtxProvider(TrainProvider):
    train_type = TrainType.KTX

    def __init__(self) -> None:
        self._clients: ClientCache = ClientCache(_make_korail)
        self._raw = RawTrainCache()

    # ------------------------------------------------------------- helpers
    def _client(self, credential: Credential):
        return self._clients.get(credential.login_id, credential.password)

    @staticmethod
    def _train_id(t) -> str:
        return f"ktx-{t.run_date}-{t.train_no}-{t.dep_code}-{t.arr_code}-{t.dep_time[:4]}"

    def _to_option(self, t) -> TrainOption:
        return TrainOption(
            train_id=self._train_id(t),
            train_type=TrainType.KTX,
            train_name=f"{t.train_type_name} {t.train_no}",
            dep_station=t.dep_name,
            arr_station=t.arr_name,
            dep_time=parse_dt(t.dep_date, t.dep_time),
            arr_time=parse_dt(getattr(t, "arr_date", t.dep_date), t.arr_time),
            general_available=t.has_general_seat(),
            special_available=t.has_special_seat(),
            waiting_available=t.has_general_waiting_list(),
            general_fare=None,   # korail2 search 는 운임 미제공
            special_fare=None,
        )

    def _passengers(self, p: Passengers) -> list:
        from korail2 import AdultPassenger, ChildPassenger, SeniorPassenger  # type: ignore

        out = []
        if p.adults:
            out.append(AdultPassenger(p.adults))
        if p.children:
            out.append(ChildPassenger(p.children))
        if p.seniors:
            out.append(SeniorPassenger(p.seniors))
        return out or [AdultPassenger(1)]

    # -------------------------------------------------------------- search
    def search(self, credential, dep, arr, date, time, *, passengers, limit=10, include_no_seats=True) -> list[TrainOption]:
        from korail2 import NoResultsError, TrainType as KTrainType  # type: ignore

        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)

        # 직통 조회
        direct_options = []
        with lock:
            try:
                trains = client.search_train(
                    dep, arr, date, time,
                    train_type=KTrainType.KTX,
                    passengers=self._passengers(passengers),
                    include_no_seats=include_no_seats,
                )
            except NoResultsError:
                trains = []
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"KTX 조회 오류: {exc}", code="search_error") from exc

        for t in trains[: limit or len(trains)]:
            self._raw.put(self._train_id(t), t)
            direct_options.append(self._to_option(t))

        # 환승 조회
        transfer_options = self._search_transfer(
            client, lock, credential, dep, arr, date, time,
            passengers=passengers, limit=limit, include_no_seats=include_no_seats,
        )

        # 직통 + 환승 합쳐서 출발시간순 정렬
        all_options = direct_options + transfer_options
        all_options.sort(key=lambda o: o.dep_time)
        return all_options[: limit or len(all_options)]

    def _search_transfer(
        self, client, lock, credential, dep, arr, date, time, *, passengers, limit=10, include_no_seats=True
    ) -> list[TrainOption]:
        """환승 열차 조회 (radJobId=2). 2개씩 쌍으로 묶어 TrainOption 1건으로 반환."""
        import json

        from korail2.korail2 import KORAIL_SEARCH_SCHEDULE

        headers, sid = client._get_auth_headers_and_sid(KORAIL_SEARCH_SCHEDULE)
        psg = self._passengers(passengers)
        from functools import reduce
        from korail2 import AdultPassenger, ChildPassenger, SeniorPassenger  # type: ignore

        adult_count = reduce(lambda a, b: a + b.count, [p for p in psg if isinstance(p, AdultPassenger)], 0)
        child_count = reduce(lambda a, b: a + b.count, [p for p in psg if isinstance(p, ChildPassenger)], 0)
        senior_count = reduce(lambda a, b: a + b.count, [p for p in psg if isinstance(p, SeniorPassenger)], 0)

        data = {
            "Device": client._device,
            "radJobId": "2",  # 환승
            "selGoTrain": "100",  # KTX
            "txtCardPsgCnt": "0",
            "txtGdNo": "",
            "txtGoAbrdDt": date,
            "txtGoEnd": arr,
            "txtGoHour": time,
            "txtGoStart": dep,
            "txtJobDv": "",
            "txtMenuId": "11",
            "txtPsgFlg_1": adult_count,
            "txtPsgFlg_2": child_count,
            "txtPsgFlg_8": 0,
            "txtPsgFlg_3": senior_count,
            "txtPsgFlg_4": "0",
            "txtPsgFlg_5": "0",
            "txtSeatAttCd_2": "000",
            "txtSeatAttCd_3": "000",
            "txtSeatAttCd_4": "015",
            "txtTrnGpCd": "100",
            "Version": client._version,
        }

        with lock:
            try:
                r = client._session.post(KORAIL_SEARCH_SCHEDULE, params=data, headers=headers)
                j = json.loads(r.text)
            except Exception as exc:  # noqa: BLE001
                # 환승 조회 실패는 무시 (직통 결과만 반환)
                return []

        if j.get("strResult") != "SUCC":
            return []

        infos = j.get("trn_infos", {}).get("trn_info", [])
        if not infos:
            return []

        # seq=1, seq=2 쌍으로 묶기
        from korail2.korail2 import Train as KTrain

        options: list[TrainOption] = []
        i = 0
        while i < len(infos) - 1:
            t1 = infos[i]
            t2 = infos[i + 1]
            seq1 = t1.get("h_chg_trn_seq", "")
            seq2 = t2.get("h_chg_trn_seq", "")
            if seq1 == "1" and seq2 == "2":
                # 환승 쌍
                train1 = KTrain(t1)
                train2 = KTrain(t2)
                transfer_id = f"ktx-transfer-{date}-{train1.train_no}-{train2.train_no}-{train1.dep_time[:4]}"
                # raw 캐시에 양쪽 열차 저장 (예약 시 사용)
                self._raw.put(transfer_id, (train1, train2))
                self._raw.put(self._train_id(train1), train1)
                self._raw.put(self._train_id(train2), train2)

                gen1 = train1.has_general_seat()
                gen2 = train2.has_general_seat()
                spe1 = train1.has_special_seat()
                spe2 = train2.has_special_seat()

                opt = TrainOption(
                    train_id=transfer_id,
                    train_type=TrainType.KTX,
                    train_name=f"{train1.train_type_name} {train1.train_no}",
                    dep_station=train1.dep_name,
                    arr_station=train2.arr_name,
                    dep_time=parse_dt(train1.dep_date, train1.dep_time),
                    arr_time=parse_dt(getattr(train2, "arr_date", train2.dep_date), train2.arr_time),
                    general_available=gen1 and gen2,
                    special_available=spe1 and spe2,
                    waiting_available=False,
                    is_transfer=True,
                    transfer_station=train1.arr_name,
                    transfer_train_name=f"{train2.train_type_name} {train2.train_no}",
                )
                if include_no_seats or opt.any_available:
                    options.append(opt)
                i += 2
            else:
                i += 1

        return options

    # --------------------------------------------------------------- seats
    def seats(self, credential, train, *, seat_class=None, car_no=None, available_only=False) -> list[CarSeats]:
        raise ProviderError(
            "실연동(KTX) 모드에서는 상세 좌석 조회를 아직 지원하지 않습니다. "
            "일반실/특실 예약 가능 여부는 조회 목록을 참고하세요.",
            code="not_supported",
        )

    # ------------------------------------------------------------- reserve
    def reserve(self, credential, train, *, passengers, seat_class=SeatClass.GENERAL) -> Reservation:
        from korail2 import ReserveOption, SoldOutError  # type: ignore

        raw = self._raw.get(train.train_id)
        if raw is None:
            raise ProviderError(
                "예약 대상 열차 정보가 만료되었습니다. 다시 조회 후 예약하세요.",
                code="stale_train",
            )
        option = (
            ReserveOption.SPECIAL_FIRST
            if seat_class is SeatClass.SPECIAL
            else ReserveOption.GENERAL_FIRST
        )
        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)
        with lock:
            try:
                rsv = client.reserve(raw, passengers=self._passengers(passengers), option=option)
            except SoldOutError as exc:
                raise ProviderError("매진되어 예약에 실패했습니다.", code="sold_out") from exc
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"KTX 예약 오류: {exc}", code="reserve_error") from exc
            # reserve() 반환값은 좌석 정보가 누락됨(라이브러리 버그).
            # 좌석 정보가 포함된 예약 목록에서 해당 예약을 다시 조회한다.
            try:
                enriched = self._reservations_with_seats(client)
                matched = next((r for r in enriched if r.rsv_id == rsv.rsv_id), rsv)
            except Exception:  # noqa: BLE001
                matched = rsv
        return self._reservation_to_model(matched, seat_class, passengers)

    # -------------------------------------------------- list_reservations
    def list_reservations(self, credential) -> list[Reservation]:
        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)
        with lock:
            try:
                items = self._reservations_with_seats(client)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"KTX 예약 목록 오류: {exc}", code="list_error") from exc
        return [self._reservation_to_model(r) for r in items]

    @staticmethod
    def _reservations_with_seats(client) -> list:
        """예약 목록을 조회하되, 좌석번호(h_srcar_no, h_seat_no 등)를 Reservation 객체에 주입한다.

        korail2-ncard 의 Reservation.__init__ 이 좌석 필드를 파싱하지 않아
        getattr(r, 'car_no') 가 항상 None. 여기서 raw dict 를 보존하여 보완한다.
        """
        import json

        from korail2.korail2 import KORAIL_MYRESERVATIONLIST, Reservation as KReservation

        data = {"Device": client._device, "Version": client._version, "Key": client._key}
        r = client._session.get(KORAIL_MYRESERVATIONLIST, params=data)
        j = json.loads(r.text)
        if j.get("strResult") != "SUCC":
            return []
        reserves = []
        for info in j.get("jrny_infos", {}).get("jrny_info", []):
            for tinfo in info.get("train_infos", {}).get("train_info", []):
                rsv = KReservation(tinfo)
                # 좌석 정보 보강 (라이브러리 미파싱 필드)
                rsv.car_no = tinfo.get("h_srcar_no") or None
                rsv.seat_no = tinfo.get("h_seat_no") or None
                rsv.seat_no_end = tinfo.get("h_seat_no_end") or None
                reserves.append(rsv)
        return reserves

    # -------------------------------------------------------------- cancel
    def cancel(self, credential, reservation_id) -> Reservation:
        client = self._client(credential)
        lock = self._clients.lock_for(credential.login_id)
        with lock:
            try:
                items = self._reservations_with_seats(client)
                target = next((r for r in items if r.rsv_id == reservation_id), None)
                if target is None:
                    raise ProviderError(f"예약을 찾을 수 없습니다: {reservation_id}", code="not_found")
                self._cancel_reservation(client, target)
            except ProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"KTX 취소 오류: {exc}", code="cancel_error") from exc
        model = self._reservation_to_model(target)
        model.status = ReservationStatus.CANCELLED
        return model

    @staticmethod
    def _cancel_reservation(client, rsv) -> None:
        """예약 취소 (korail2-ncard 버그 우회).

        라이브러리의 `Korail.cancel()` 은 GET 요청 파라미터를 `data=`(본문)로 보내
        서버가 400 을 반환한다. 정상 동작하는 `reservations()` 처럼 `params=`
        (쿼리스트링)로 전송하면 취소가 성공한다.
        """
        import json

        from korail2.korail2 import KORAIL_CANCEL

        data = {
            "Device": client._device,
            "Version": client._version,
            "Key": client._key,
            "txtPnrNo": rsv.rsv_id,
            "txtJrnySqno": rsv.journey_no,
            "txtJrnyCnt": rsv.journey_cnt,
            "hidRsvChgNo": rsv.rsv_chg_no,
        }
        r = client._session.get(KORAIL_CANCEL, params=data)
        j = json.loads(r.text)
        if j.get("strResult") != "SUCC":
            msg = j.get("h_msg_txt") or j.get("h_msg_cd") or "알 수 없는 오류"
            raise ProviderError(f"KTX 취소 실패: {msg}", code="cancel_failed")

    # ------------------------------------------------------------- mapping
    @staticmethod
    def _seat_no(r) -> str | None:
        """korail2 Reservation 의 호차/좌석번호를 표시 문자열로 변환.

        Reservation 은 car_no, seat_no, seat_no_end 를 제공한다.
        복수 좌석이면 "3호차 5A~7A" 형태, 좌석 미배정이면 None.
        """
        car = getattr(r, "car_no", None)
        start = getattr(r, "seat_no", None)
        end = getattr(r, "seat_no_end", None)
        if not start:
            return None
        rng = f"{start}~{end}" if end and end != start else f"{start}"
        return f"{car}호차 {rng}".strip() if car else rng

    def _reservation_to_model(
        self, r, seat_class: SeatClass = SeatClass.GENERAL, passengers: Passengers | None = None
    ) -> Reservation:
        deadline = None
        bl_date = getattr(r, "buy_limit_date", None)
        bl_time = getattr(r, "buy_limit_time", None)
        if bl_date and bl_time:
            deadline = parse_dt(bl_date, bl_time)
        count = getattr(r, "seat_no_count", None) or (passengers.total if passengers else 1)
        return Reservation(
            reservation_id=r.rsv_id,
            train_type=TrainType.KTX,
            train_name=f"{r.train_type_name} {r.train_no}",
            dep_station=r.dep_name,
            arr_station=r.arr_name,
            dep_time=parse_dt(r.dep_date, r.dep_time),
            arr_time=parse_dt(getattr(r, "arr_date", r.dep_date), r.arr_time),
            seat_class=seat_class,
            seat_no=self._seat_no(r),
            passengers=passengers or Passengers(adults=count),
            fare=int(getattr(r, "price", 0) or 0),
            status=ReservationStatus.RESERVED,
            deadline=deadline,
            created_at=datetime.now(),
        )
