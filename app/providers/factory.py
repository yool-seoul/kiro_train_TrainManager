"""Provider 팩토리.

`data_source` 설정에 따라 Mock 또는 실연동 provider 를 돌려준다.
provider 는 예약 상태를 메모리에 들고 있으므로 train_type 별 싱글턴으로 관리한다.
"""

from __future__ import annotations

from app.config import get_settings
from app.providers.base import TrainProvider
from app.schemas import TrainType

_instances: dict[tuple[str, TrainType], TrainProvider] = {}


def get_provider(train_type: TrainType) -> TrainProvider:
    """train_type 에 맞는 provider 싱글턴 반환."""
    settings = get_settings()
    key = (settings.data_source, train_type)
    if key in _instances:
        return _instances[key]

    provider: TrainProvider
    if settings.data_source == "mock":
        from app.providers.mock import MockProvider

        provider = MockProvider(train_type)
    else:  # live
        if train_type is TrainType.KTX:
            from app.providers.ktx import KtxProvider

            provider = KtxProvider()
        else:
            from app.providers.srt import SrtProvider

            provider = SrtProvider()

    _instances[key] = provider
    return provider


def reset_providers() -> None:
    """테스트/설정변경 시 싱글턴 초기화."""
    _instances.clear()
