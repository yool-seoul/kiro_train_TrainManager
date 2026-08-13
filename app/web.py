"""웹(프레젠테이션) 공통 설정: Jinja2 템플릿 + 필터."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _fmt_time(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        return ""
    return value.strftime("%m/%d %H:%M")


def _fmt_won(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,}원"


templates.env.filters["fmt_time"] = _fmt_time
templates.env.filters["fmt_won"] = _fmt_won
