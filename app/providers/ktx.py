"""KTX/Korail provider (실연동).

`korail2-ncard` 라이브러리를 감싼다. 현재는 골격만 있으며,
`data_source=live` 로 전환하고 아래 TODO 를 채우면 동작한다.

참고(k-skill/ktx-booking):
- 원본 korail2 는 anti-bot(Dynapath) 때문에 MACRO ERROR 가능 → korail2-ncard 사용.
- 로그인: Korail(login_id, password)
- 조회: korail.search_train(dep, arr, date, time, ...)
- 예약: korail.reserve(train, passengers=[...], option=...)
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


class KtxProvider(TrainProvider):
    """korail2-ncard 어댑터."""

    train_type = TrainType.KTX

    def __init__(self) -> None:
        # 실연동 시: from korail2 import Korail 를 지연 import
        # (Mock 모드에서 미설치여도 앱이 뜨도록 __init__ 에서 import 하지 않음)
        self._not_impl = "KTX 실연동은 아직 구현되지 않았습니다. data_source=mock 을 사용하세요."

    def _client(self, credential: Credential):  # pragma: no cover - 실연동 전 미사용
        try:
            from korail2 import Korail  # type: ignore
        except ImportError as exc:
            raise ProviderError(
                "korail2-ncard 미설치. `pip install korail2-ncard pycryptodome` 후 사용.",
                code="dependency_missing",
            ) from exc
        return Korail(credential.login_id, credential.password)

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
