"""Pydantic 스키마 (요청/응답 DTO 및 도메인 모델)."""

from app.schemas.train import (
    CarSeats,
    Credential,
    Passengers,
    Reservation,
    ReservationStatus,
    SeatClass,
    SeatDetail,
    TrainOption,
    TrainType,
    WatchJob,
    WatchStatus,
)

__all__ = [
    "CarSeats",
    "Credential",
    "Passengers",
    "Reservation",
    "ReservationStatus",
    "SeatClass",
    "SeatDetail",
    "TrainOption",
    "TrainType",
    "WatchJob",
    "WatchStatus",
]
