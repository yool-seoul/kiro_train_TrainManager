"""실연동 provider 공용 유틸.

- 계정(login_id)별 로그인 client 를 캐시하고, 계정별 Lock 으로 호출을 직렬화한다.
  (라이브러리 세션 공유/anti-bot 문제를 피하기 위해 동시 호출을 막는다.)
- search 시 라이브러리 원본 열차 객체를 train_id 로 캐시해, reserve/cancel 에서 다시 찾는다.
  (우리 TrainOption 만으로는 라이브러리 reserve 에 필요한 내부 필드를 복원할 수 없기 때문.)
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable, Generic, TypeVar

C = TypeVar("C")


class ClientCache(Generic[C]):
    """login_id -> client 캐시 + 계정별 Lock."""

    def __init__(self, factory: Callable[[str, str], C]) -> None:
        self._factory = factory
        self._clients: dict[str, C] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def lock_for(self, login_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(login_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[login_id] = lock
            return lock

    def get(self, login_id: str, password: str) -> C:
        with self._guard:
            client = self._clients.get(login_id)
        if client is None:
            client = self._factory(login_id, password)  # 로그인 발생
            with self._guard:
                self._clients[login_id] = client
        return client

    def invalidate(self, login_id: str) -> None:
        with self._guard:
            self._clients.pop(login_id, None)


class RawTrainCache:
    """train_id -> 라이브러리 원본 열차 객체 (예약/좌석조회 재사용)."""

    def __init__(self, max_size: int = 500) -> None:
        self._data: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._max = max_size

    def put(self, train_id: str, obj: Any) -> None:
        with self._lock:
            if len(self._data) >= self._max:
                # 단순 정책: 가장 오래된 절반 제거
                for key in list(self._data.keys())[: self._max // 2]:
                    self._data.pop(key, None)
            self._data[train_id] = obj

    def get(self, train_id: str) -> Any | None:
        with self._lock:
            return self._data.get(train_id)


def parse_dt(date: str | None, time: str | None) -> datetime:
    """YYYYMMDD + HHMMSS → datetime. 실패 시 now()."""
    try:
        return datetime.strptime((date or "") + (time or ""), "%Y%m%d%H%M%S")
    except (ValueError, TypeError):
        return datetime.now()
