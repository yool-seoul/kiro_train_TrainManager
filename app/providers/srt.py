"""SRT provider (실연동).

`SRTrain` 라이브러리(`import SRT`)를 감싼다. 현재는 골격만 있으며,
`data_source=live` 로 전환하고 아래 TODO 를 채우면 동작한다.

참고(k-skill/srt-booking):
- 로그인: SRT(login_id, password)
- 조회: srt.search_train(dep, arr, date, time, time_limit=...)
- 예약: srt.reserve(train, passengers=[Adult(n)], special_seat=SeatType...)
- 취소: srt.get_reservations() / srt.cancel(reservation)
"""

from __future__ import annotations

from app.providers.base import ProviderError, TrainProvider
from app.schemas import (
    CarSeats,
    Credential,
    Passengers,
    Reservation,
    SeatClass,
    TrainOption,
    TrainType,
)


class SrtProvider(TrainProvider):
    """SRTrain 어댑터."""

    train_type = TrainType.SRT

    def __init__(self) -> None:
        self._not_impl = "SRT 실연동은 아직 구현되지 않았습니다. data_source=mock 을 사용하세요."

    def _client(self, credential: Credential):  # pragma: no cover - 실연동 전 미사용
        try:
            from SRT import SRT  # type: ignore
        except ImportError as exc:
            raise ProviderError(
                "SRTrain 미설치. `pip install SRTrain` 후 사용.",
                code="dependency_missing",
            ) from exc
        return SRT(credential.login_id, credential.password)

    def search(self, credential, dep, arr, date, time, *, passengers, limit=10, include_no_seats=True) -> list[TrainOption]:  # noqa: D102
        raise ProviderError(self._not_impl, code="not_implemented")

    def seats(self, credential, train, *, seat_class=None, car_no=None, available_only=False) -> list[CarSeats]:  # noqa: D102
        raise ProviderError(self._not_impl, code="not_implemented")

    def reserve(self, credential, train, *, passengers, seat_class=SeatClass.GENERAL) -> Reservation:  # noqa: D102
        raise ProviderError(self._not_impl, code="not_implemented")

    def list_reservations(self, credential) -> list[Reservation]:  # noqa: D102
        raise ProviderError(self._not_impl, code="not_implemented")

    def cancel(self, credential, reservation_id) -> Reservation:  # noqa: D102
        raise ProviderError(self._not_impl, code="not_implemented")
