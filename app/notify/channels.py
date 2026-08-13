"""알림 채널 구현체."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from app.notify.base import Notifier


class NullNotifier(Notifier):
    """비활성 채널(기본). 아무것도 보내지 않는다."""

    def send(self, text: str) -> None:  # noqa: D102
        return None


class ConsoleNotifier(Notifier):
    """stdout 출력(로컬 디버그용)."""

    def send(self, text: str) -> None:  # noqa: D102
        print("[NOTIFY]\n" + text, flush=True)


class TelegramNotifier(Notifier):
    """텔레그램 봇 알림.

    준비물:
    - 봇 생성(@BotFather) → 봇 토큰
    - 봇과 1회 대화 시작 후 chat_id 확인
      (https://api.telegram.org/bot<token>/getUpdates 의 chat.id)
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._token = bot_token
        self._chat_id = chat_id

    def send(self, text: str) -> None:  # noqa: D102
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": self._chat_id, "text": text}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            body = json.loads(resp.read().decode())
        if not body.get("ok"):
            raise RuntimeError(f"Telegram 전송 실패: {body}")
