"""도메인 모델 및 DTO.

KTX(Korail)와 SRT 는 내부 필드가 다르지만, 웹/서비스 레이어에서는
아래의 통일된 모델만 다룬다. 각 provider 어댑터가 자사 응답을 이 모델로 변환한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TrainType(str, Enum):
    """열차 운영사 구분."""

    KTX = "ktx"
    SRT = "srt"


class SeatClass(str, Enum):
    """객실 등급."""

    GENERAL = "general"   # 일반실
    SPECIAL = "special"   # 특실


class ReservationStatus(str, Enum):
    """예약 상태."""

    RESERVED = "reserved"          # 선점 완료, 결제 대기
    PAID = "paid"                  # 결제 완료 (실연동에서만 의미)
    CANCELLED = "cancelled"        # 취소됨
    EXPIRED = "expired"            # 구입기한 초과


class WatchStatus(str, Enum):
    """자동 예약대기(watch) 작업 상태."""

    WATCHING = "watching"          # 감시 중 (좌석 대기)
    RESERVED = "reserved"          # 좌석 선점 성공 → 결제 필요
    STOPPED = "stopped"            # 사용자가 중단
    EXPIRED = "expired"            # 최대 감시 시간 초과
    FAILED = "failed"              # 오류로 종료


class Passengers(BaseModel):
    """승객 구성."""

    adults: int = Field(default=1, ge=0, le=9)
    children: int = Field(default=0, ge=0, le=9)
    seniors: int = Field(default=0, ge=0, le=9)

    @property
    def total(self) -> int:
        return self.adults + self.children + self.seniors


class Credential(BaseModel):
    """열차 예매 계정 자격증명 (Google Sheet 등에서 로드)."""

    provider: TrainType
    login_id: str
    password: str = Field(repr=False)          # repr 에 노출 안 함
    ncard_no: str | None = Field(default=None, repr=False)
    label: str | None = None                   # 사용자 구분용 표시명

    def masked(self) -> str:
        """로그/화면 노출용 마스킹 문자열."""
        uid = self.login_id
        if len(uid) <= 4:
            shown = uid[:1]
        else:
            shown = uid[:3]
        return f"{shown}***({self.provider.value})"


class SeatDetail(BaseModel):
    """개별 좌석 정보."""

    seat_no: str                               # 예: "11A"
    seat_class: SeatClass = SeatClass.GENERAL
    is_available: bool = True
    direction: str | None = None               # forward | backward
    position: str | None = None                # window | aisle
    power_outlet: str | None = None            # direct | adjacent | none
    near_door: bool = False


class CarSeats(BaseModel):
    """호차 단위 좌석 묶음."""

    car_no: int
    seat_class: SeatClass = SeatClass.GENERAL
    available_seat_count: int = 0
    seats: list[SeatDetail] = Field(default_factory=list)

    @property
    def available_seats(self) -> list[str]:
        return [s.seat_no for s in self.seats if s.is_available]


class TrainOption(BaseModel):
    """조회 결과의 열차 1건."""

    train_id: str                              # provider 가 만든 stable selector
    train_type: TrainType
    train_name: str                            # 예: "KTX 101", "SRT 351"
    dep_station: str
    arr_station: str
    dep_time: datetime
    arr_time: datetime
    general_available: bool = False
    special_available: bool = False
    waiting_available: bool = False            # 예약대기 가능 여부
    general_fare: int | None = None
    special_fare: int | None = None

    @property
    def any_available(self) -> bool:
        return self.general_available or self.special_available


class Reservation(BaseModel):
    """예약 결과."""

    reservation_id: str
    train_type: TrainType
    train_name: str
    dep_station: str
    arr_station: str
    dep_time: datetime
    arr_time: datetime
    seat_class: SeatClass
    seat_no: str | None = None
    passengers: Passengers
    fare: int
    status: ReservationStatus = ReservationStatus.RESERVED
    deadline: datetime | None = None           # 구입기한
    created_at: datetime = Field(default_factory=datetime.now)


class WatchJob(BaseModel):
    """자동 예약대기 작업.

    좌석이 없을 때 주기적으로 재조회하여, 좌석이 생기면 자동으로 선점(reserve)하고
    결제 필요 상태로 사용자에게 알린다.
    """

    job_id: str
    train_type: TrainType
    dep_station: str
    arr_station: str
    date: str                                  # YYYYMMDD
    time: str                                  # HHMMSS (희망 시작 시각)
    passengers: Passengers
    seat_class: SeatClass = SeatClass.GENERAL
    credential_label: str | None = None
    status: WatchStatus = WatchStatus.WATCHING
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime | None = None
    last_checked_at: datetime | None = None
    attempts: int = 0
    reservation: Reservation | None = None     # 선점 성공 시 채워짐
    message: str | None = None                 # 상태 설명/오류 메시지
