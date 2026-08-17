"""WatchService - 자동 예약대기(폴링 → 자동 선점 → 결제 알림).

좌석이 없을 때 사용자가 watch 를 등록하면, 백그라운드 스레드가 주기적으로 재조회한다.
좌석이 생기면 즉시 선점(reserve)하고 상태를 RESERVED 로 바꿔 "결제 필요"를 알린다.

설계 노트:
- provider(korail2/SRTrain)는 blocking I/O 이므로 asyncio 대신 daemon 스레드를 쓴다.
- anti-bot/계정 보호를 위해 폴링 주기는 하한(min_interval)을 두고 보수적으로 유지한다.
- 동시 watch 개수와 최대 감시 시간을 제한한다.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta

from app.config import get_settings
from app.providers.base import ProviderError
from app.schemas import (
    Passengers,
    SeatClass,
    TrainOption,
    TrainType,
    WatchJob,
    WatchStatus,
)
from app.services.booking import get_booking_service


class WatchService:
    def __init__(self) -> None:
        self._jobs: dict[str, WatchJob] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- public
    def list_jobs(self) -> list[WatchJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> WatchJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create_watch(
        self,
        train_type: TrainType,
        dep: str,
        arr: str,
        date: str,
        time: str,
        *,
        passengers: Passengers,
        seat_class: SeatClass = SeatClass.GENERAL,
        credential_label: str | None = None,
        target_train_id: str | None = None,
        target_train_name: str | None = None,
    ) -> WatchJob:
        settings = get_settings()
        with self._lock:
            active = sum(1 for j in self._jobs.values() if j.status is WatchStatus.WATCHING)
            if active >= settings.watch_max_jobs:
                raise ProviderError(
                    f"동시 감시 개수 제한({settings.watch_max_jobs})을 초과했습니다.",
                    code="too_many_watches",
                )
            # 동일 열차에 대한 활성 대기가 이미 있으면 중복 등록 방지
            if target_train_id:
                for j in self._jobs.values():
                    if (
                        j.status is WatchStatus.WATCHING
                        and j.target_train_id == target_train_id
                    ):
                        raise ProviderError(
                            "해당 열차는 이미 대기 중입니다.",
                            code="duplicate_watch",
                        )

        now = datetime.now()
        job = WatchJob(
            job_id=uuid.uuid4().hex[:12],
            train_type=train_type,
            dep_station=dep,
            arr_station=arr,
            date=date,
            time=time,
            passengers=passengers,
            seat_class=seat_class,
            credential_label=credential_label,
            target_train_id=target_train_id,
            target_train_name=target_train_name,
            status=WatchStatus.WATCHING,
            created_at=now,
            expires_at=now + timedelta(seconds=settings.watch_max_duration_sec),
            message=(
                f"{target_train_name} 좌석을 감시하는 중입니다."
                if target_train_name
                else "좌석을 감시하는 중입니다."
            ),
        )
        stop_event = threading.Event()
        with self._lock:
            self._jobs[job.job_id] = job
            self._stop_events[job.job_id] = stop_event

        thread = threading.Thread(target=self._run, args=(job.job_id, stop_event), daemon=True)
        thread.start()
        return job

    def stop(self, job_id: str) -> WatchJob | None:
        """감시 중인 작업만 중단한다.

        이미 예약 완료(RESERVED)되었거나 종료(EXPIRED/FAILED/STOPPED)된 작업은
        중단 대상이 아니다 → 상태를 바꾸지 않고 그대로 반환한다.
        (예약이 성사된 뒤에는 대기를 취소할 수 없어야 하므로.)
        """
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._stop_events.get(job_id)
        if job is None:
            return None
        if job.status is not WatchStatus.WATCHING:
            return job
        if event is not None:
            event.set()
        job.status = WatchStatus.STOPPED
        job.message = "사용자가 감시를 중단했습니다."
        return job

    # -------------------------------------------------------------- internal
    def _run(self, job_id: str, stop_event: threading.Event) -> None:
        settings = get_settings()
        interval = max(settings.watch_poll_interval_sec, settings.watch_min_interval_sec)
        booking = get_booking_service()
        job = self._jobs[job_id]

        while not stop_event.is_set():
            now = datetime.now()
            if job.expires_at and now >= job.expires_at:
                job.status = WatchStatus.EXPIRED
                job.message = "최대 감시 시간이 초과되어 종료했습니다."
                return

            job.attempts += 1
            job.last_checked_at = now
            try:
                trains = booking.search(
                    job.train_type,
                    job.dep_station,
                    job.arr_station,
                    job.date,
                    job.time,
                    passengers=job.passengers,
                    credential_label=job.credential_label,
                    include_no_seats=False,
                )
                candidate = self._pick(trains, job.seat_class, job.target_train_id)
                if candidate is not None:
                    reservation = booking.reserve(
                        candidate,
                        passengers=job.passengers,
                        seat_class=job.seat_class,
                        credential_label=job.credential_label,
                    )
                    job.reservation = reservation
                    job.status = WatchStatus.RESERVED
                    job.message = (
                        f"좌석 선점 완료: {reservation.train_name} "
                        f"{reservation.seat_no or ''}. 구입기한 전에 결제하세요."
                    )
                    self._notify_reserved(job)
                    return
            except ProviderError as exc:
                # 매진(sold_out) 등 일시적 사유면 계속 감시, 그 외는 메시지만 갱신
                job.message = f"조회 중: {exc.message}"

            # 다음 폴링까지 대기 (중단 시 즉시 빠져나옴)
            if stop_event.wait(interval):
                return

    @staticmethod
    def _notify_reserved(job: WatchJob) -> None:
        """선점 성공 시 메신저 알림. 알림 실패가 감시 흐름을 깨지 않도록 예외를 삼킨다."""
        try:
            from app.notify import get_notifier

            get_notifier().notify_reserved(job)
        except Exception as exc:  # noqa: BLE001
            job.message = (job.message or "") + f" (알림 전송 실패: {exc})"

    @staticmethod
    def _pick(
        trains: list[TrainOption],
        seat_class: SeatClass,
        target_train_id: str | None = None,
    ) -> TrainOption | None:
        """예약할 열차 선택.

        - target_train_id 가 있으면 그 열차만 대상으로 하고, 해당 좌석 등급이
          가능해질 때까지 기다린다(가능하면 반환).
        - 없으면 희망 좌석 등급이 가능한 가장 이른 열차를 선택한다.
        """
        def _has_class(train: TrainOption) -> bool:
            if seat_class is SeatClass.SPECIAL:
                return train.special_available
            return train.general_available

        if target_train_id is not None:
            for train in trains:
                if train.train_id == target_train_id and _has_class(train):
                    return train
            return None

        for train in sorted(trains, key=lambda t: t.dep_time):
            if _has_class(train):
                return train
        return None


_watch_service: WatchService | None = None


def get_watch_service() -> WatchService:
    global _watch_service
    if _watch_service is None:
        _watch_service = WatchService()
    return _watch_service
