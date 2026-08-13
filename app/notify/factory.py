"""Notifier 팩토리."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.notify.base import Notifier


@lru_cache
def get_notifier() -> Notifier:
    from app.notify.channels import ConsoleNotifier, NullNotifier, TelegramNotifier

    s = get_settings()
    if s.notify_channel == "telegram":
        if not s.telegram_bot_token or not s.telegram_chat_id:
            # 설정 미비 시 조용히 비활성 (감시 흐름을 막지 않음)
            return NullNotifier()
        return TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
    if s.notify_channel == "console":
        return ConsoleNotifier()
    return NullNotifier()


def reset_notifier() -> None:
    get_notifier.cache_clear()
