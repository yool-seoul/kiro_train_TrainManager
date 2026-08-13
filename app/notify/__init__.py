"""알림(메신저) 모듈.

자동 예약대기가 좌석을 선점하면 사용자에게 메신저로 알린다(D8-1=c).

- Notifier: 추상 인터페이스
- NullNotifier: 비활성(기본)
- ConsoleNotifier: stdout (로컬 디버그)
- TelegramNotifier: 텔레그램 봇 (봇 토큰 + chat_id)
- (Kakao 등은 후속 확장 포인트)
"""

from app.notify.base import (
    Notifier,
    build_reservation_message,
    build_reserved_message,
)
from app.notify.factory import get_notifier

__all__ = [
    "Notifier",
    "build_reservation_message",
    "build_reserved_message",
    "get_notifier",
]
