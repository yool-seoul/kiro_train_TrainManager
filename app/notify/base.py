"""Notifier 추상 인터페이스 및 메시지 빌더."""

from __future__ import annotations

import abc

from app.schemas import Reservation, WatchJob


class Notifier(abc.ABC):
    """알림 채널.

    구현체는 `send(text)` 만 구현하면 된다. 예외는 호출부에서 삼켜서
    알림 실패가 예약/감시 흐름을 깨지 않도록 한다.
    """

    @abc.abstractmethod
    def send(self, text: str) -> None:
        """텍스트 메시지 전송."""

    def notify_reserved(self, job: WatchJob) -> None:
        """자동 예약대기 선점 성공 알림."""
        self.send(build_reserved_message(job))

    def notify_reservation(self, reservation: Reservation) -> None:
        """수동 예약(선점) 성공 알림."""
        self.send(build_reservation_message(reservation))


def _is_mock() -> bool:
    """현재 data_source 가 mock 인지 여부."""
    from app.config import get_settings

    return get_settings().data_source == "mock"


def build_reservation_message(r: Reservation, *, header: str | None = None) -> str:
    """예약(선점) 성공 메시지 생성 (예약 객체 기준)."""
    default_header = "🚄 좌석 선점 완료 — 결제가 필요합니다."
    if _is_mock():
        default_header = "[테스트] " + default_header
    lines = [header or default_header]
    lines.append(f"{r.train_name} {r.dep_station}→{r.arr_station}")
    lines.append(f"출발: {r.dep_time:%m/%d %H:%M}")
    seat = f" {r.seat_no}" if r.seat_no else ""
    cls = "특실" if r.seat_class.value == "special" else "일반실"
    lines.append(f"좌석: {cls}{seat}")
    lines.append(f"운임: {r.fare:,}원 ({r.passengers.total}명)")
    lines.append(f"예약번호: {r.reservation_id}")
    if r.deadline:
        lines.append(f"구입기한: {r.deadline:%m/%d %H:%M} 까지")
    lines.append("결제는 공식 KTX/SRT 화면에서 진행하세요.")
    return "\n".join(lines)


def build_reserved_message(job: WatchJob) -> str:
    """자동 예약대기 선점 성공 메시지 생성."""
    r = job.reservation
    if r is not None:
        return build_reservation_message(r)
    lines = [
        "🚄 좌석 선점 완료 — 결제가 필요합니다.",
        f"{job.train_type.value.upper()} {job.dep_station}→{job.arr_station}",
        "결제는 공식 KTX/SRT 화면에서 진행하세요.",
    ]
    return "\n".join(lines)
