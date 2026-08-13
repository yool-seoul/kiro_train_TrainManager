"""애플리케이션 설정.

환경변수(.env) 또는 OS 환경변수에서 값을 읽는다.
`pydantic-settings` 를 사용해 타입 검증과 기본값을 한 곳에서 관리한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """전역 설정.

    - `data_source` 가 "mock" 이면 실제 Korail/SRT 로 나가지 않고 가짜 데이터를 쓴다.
      실연동 전환은 이 값을 "live" 로 바꾸는 것만으로 이루어진다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRAINMGR_",
        extra="ignore",
    )

    # 애플리케이션
    app_name: str = "Train Manager"
    debug: bool = True
    # 세션 서명 키 (운영에서는 반드시 환경변수로 교체)
    session_secret: str = "dev-only-insecure-secret-change-me"

    # 데이터 소스: mock | live
    data_source: Literal["mock", "live"] = "mock"

    # --- 자동 예약대기(watch) 기본값 (D8 답변 반영) ---
    watch_poll_interval_sec: int = 10          # 폴링 주기(초) — D8-2: 10초
    watch_min_interval_sec: int = 10           # 하한(anti-bot 보호)
    watch_max_duration_sec: int = 30 * 60      # 최대 감시 시간(초) — D8-4: 30분
    watch_max_jobs: int = 5                    # 동시 watch 개수 제한 — D8-4: 5개

    # --- 알림(D8-1=c: 메신저) ---
    # 채널: none(비활성) | telegram | console(디버그용 stdout)
    notify_channel: Literal["none", "telegram", "console"] = "none"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # --- Google Sheets 자격증명 (D7, 미확정 시 추천값) ---
    # 접근 방식: service_account | csv_url | disabled
    credential_source: Literal["service_account", "csv_url", "disabled"] = "disabled"
    google_service_account_file: str | None = None   # 서비스 계정 JSON 경로
    google_spreadsheet_id: str | None = None
    google_worksheet_name: str = "credentials"
    google_csv_url: str | None = None                # csv_url 방식일 때


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 테스트에서는 `get_settings.cache_clear()` 로 초기화 가능."""
    return Settings()
