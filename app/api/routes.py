"""HTTP 라우터.

HTML 페이지 + HTMX 부분 렌더링을 제공한다.
- 서비스/스키마만 의존하고 provider 구체 타입은 모른다.
- 조회 결과의 TrainOption 은 hidden 필드에 JSON 으로 실어 후속 요청(좌석/예약/watch)에 전달한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.credentials import get_credential_store
from app.providers.base import ProviderError
from app.schemas import Passengers, SeatClass, TrainOption, TrainType
from app.services import get_booking_service, get_watch_service
from app.web import templates

router = APIRouter()


# ---------------------------------------------------------------- helpers
def _parse_date(value: str) -> str:
    """<input type=date> 의 YYYY-MM-DD → YYYYMMDD."""
    return value.replace("-", "").strip()


def _parse_time(value: str) -> str:
    """<input type=time> 의 HH:MM → HHMMSS."""
    return value.replace(":", "").ljust(6, "0")[:6]


def _passengers(adults: int, children: int, seniors: int) -> Passengers:
    return Passengers(adults=adults, children=children, seniors=seniors)


def _render_error(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/error.html",
        {"message": message},
        status_code=status_code,
    )


# ------------------------------------------------------------------- pages
def _default_datetime():
    """현재 시각 기준 가장 가까운 미래(다음 30분 경계)의 날짜/시각 기본값."""
    from datetime import datetime, timedelta

    now = datetime.now().replace(second=0, microsecond=0)
    add = 30 - (now.minute % 30)  # 정각/30분이면 다음 경계로 (항상 미래)
    nxt = now + timedelta(minutes=add)
    return nxt.strftime("%Y-%m-%d"), nxt.strftime("%H:%M")


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    store = get_credential_store()
    try:
        creds = store.list_credentials()
    except Exception:  # noqa: BLE001 - 자격증명 로드 실패 시에도 화면은 뜨게
        creds = []
    default_date, default_time = _default_datetime()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "settings": settings,
            "credentials": creds,
            "train_types": list(TrainType),
            "default_date": default_date,
            "default_time": default_time,
        },
    )


@router.get("/credentials", response_class=HTMLResponse)
def credentials_page(request: Request) -> HTMLResponse:
    """자격증명 소스(Google Sheet 등) 읽기 상태 진단 페이지.

    비밀번호는 화면/로그에 노출하지 않고 마스킹한다.
    보안상 debug 모드에서만 접근 가능하다(운영에서는 404).
    """
    settings = get_settings()
    if not settings.debug:
        raise HTTPException(status_code=404)
    from app.credentials import CredentialError, get_credential_store

    # 서비스 계정 이메일(공유 대상 확인용, 시크릿 아님) 추출 시도
    sa_email = None
    if settings.google_service_account_file:
        try:
            import json

            with open(settings.google_service_account_file, encoding="utf-8") as f:
                sa_email = json.load(f).get("client_email")
        except Exception:  # noqa: BLE001
            sa_email = None

    def _mask_id(sheet_id: str | None) -> str | None:
        if not sheet_id:
            return None
        if len(sheet_id) <= 8:
            return sheet_id[:2] + "…"
        return f"{sheet_id[:4]}…{sheet_id[-4:]}"

    rows: list[dict] = []
    error = None
    try:
        store = get_credential_store()
        for c in store.list_credentials():
            rows.append(
                {
                    "provider": c.provider.value,
                    "label": c.label or "",
                    "login_id": c.login_id,
                    "password_set": bool(c.password),
                    "ncard": bool(c.ncard_no),
                }
            )
    except CredentialError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    return templates.TemplateResponse(
        request,
        "credentials.html",
        {
            "settings": settings,
            "rows": rows,
            "error": error,
            "sa_email": sa_email,
            "spreadsheet_id_masked": _mask_id(settings.google_spreadsheet_id),
        },
    )


@router.get("/reservations", response_class=HTMLResponse)
def reservations_page(request: Request) -> HTMLResponse:
    booking = get_booking_service()
    try:
        items = booking.all_reservations()
    except ProviderError as exc:
        return _render_error(request, exc.message)
    return templates.TemplateResponse(
        request, "reservations.html", {"reservations": items}
    )


@router.get("/watch", response_class=HTMLResponse)
def watch_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "watch.html", {"jobs": get_watch_service().list_jobs()}
    )


# ---------------------------------------------------------- HTMX fragments
@router.post("/search", response_class=HTMLResponse)
def search(
    request: Request,
    train_type: TrainType = Form(...),
    dep: str = Form(...),
    arr: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    seat_class: SeatClass = Form(SeatClass.GENERAL),
    adults: int = Form(1),
    children: int = Form(0),
    seniors: int = Form(0),
    credential_label: str | None = Form(None),
) -> HTMLResponse:
    booking = get_booking_service()
    passengers = _passengers(adults, children, seniors)
    try:
        trains = booking.search(
            train_type,
            dep.strip(),
            arr.strip(),
            _parse_date(date),
            _parse_time(time),
            passengers=passengers,
            credential_label=credential_label or None,
            include_no_seats=True,
        )
    except ProviderError as exc:
        return _render_error(request, exc.message)

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "trains": trains,
            "seat_class": seat_class,
            "passengers": passengers,
            "credential_label": credential_label or "",
            # 자동 예약대기 등록에 필요한 원본 검색 조건 (input 값 그대로)
            "search": {
                "train_type": train_type.value,
                "dep": dep.strip(),
                "arr": arr.strip(),
                "date": date,
                "time": time,
                "adults": adults,
                "children": children,
                "seniors": seniors,
                "seat_class": seat_class.value,
            },
        },
    )


@router.post("/seats", response_class=HTMLResponse)
def seats(
    request: Request,
    train_json: str = Form(...),
    seat_class: SeatClass = Form(SeatClass.GENERAL),
    available_only: bool = Form(False),
    car_no: int | None = Form(None),
    credential_label: str | None = Form(None),
) -> HTMLResponse:
    booking = get_booking_service()
    try:
        train = TrainOption.model_validate_json(train_json)
        cars = booking.seats(
            train,
            seat_class=seat_class,
            car_no=car_no,
            available_only=available_only,
            credential_label=credential_label or None,
        )
    except ProviderError as exc:
        return _render_error(request, exc.message)

    return templates.TemplateResponse(
        request, "partials/seats.html", {"train": train, "cars": cars}
    )


@router.post("/reserve", response_class=HTMLResponse)
def reserve(
    request: Request,
    train_json: str = Form(...),
    seat_class: SeatClass = Form(SeatClass.GENERAL),
    adults: int = Form(1),
    children: int = Form(0),
    seniors: int = Form(0),
    credential_label: str | None = Form(None),
) -> HTMLResponse:
    booking = get_booking_service()
    passengers = _passengers(adults, children, seniors)
    try:
        train = TrainOption.model_validate_json(train_json)
        reservation = booking.reserve(
            train,
            passengers=passengers,
            seat_class=seat_class,
            credential_label=credential_label or None,
        )
    except ProviderError as exc:
        return _render_error(request, exc.message)

    return templates.TemplateResponse(
        request, "partials/reservation.html", {"reservation": reservation}
    )


@router.post("/reservations/cancel", response_class=HTMLResponse)
def cancel(
    request: Request,
    train_type: TrainType = Form(...),
    reservation_id: str = Form(...),
    credential_label: str | None = Form(None),
) -> HTMLResponse:
    booking = get_booking_service()
    try:
        booking.cancel(train_type, reservation_id, credential_label=credential_label or None)
    except ProviderError as exc:
        return _render_error(request, exc.message)
    # 갱신된 전체 목록을 다시 렌더
    return templates.TemplateResponse(
        request,
        "partials/reservation_list.html",
        {"reservations": booking.all_reservations()},
    )


@router.post("/watch", response_class=HTMLResponse)
def create_watch(
    request: Request,
    train_type: TrainType = Form(...),
    dep: str = Form(...),
    arr: str = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    seat_class: SeatClass = Form(SeatClass.GENERAL),
    adults: int = Form(1),
    children: int = Form(0),
    seniors: int = Form(0),
    credential_label: str | None = Form(None),
    target_train_id: str | None = Form(None),
    target_train_name: str | None = Form(None),
) -> HTMLResponse:
    watch = get_watch_service()
    try:
        watch.create_watch(
            train_type,
            dep.strip(),
            arr.strip(),
            _parse_date(date),
            _parse_time(time),
            passengers=_passengers(adults, children, seniors),
            seat_class=seat_class,
            credential_label=credential_label or None,
            target_train_id=target_train_id or None,
            target_train_name=target_train_name or None,
        )
    except ProviderError as exc:
        return _render_error(request, exc.message)
    return templates.TemplateResponse(
        request, "partials/watch_panel.html", {"jobs": watch.list_jobs()}
    )


@router.get("/watch/list", response_class=HTMLResponse)
def watch_list(request: Request) -> HTMLResponse:
    """HTMX 폴링용: watch 작업 상태 목록."""
    return templates.TemplateResponse(
        request, "partials/watch_list.html", {"jobs": get_watch_service().list_jobs()}
    )


@router.post("/watch/stop", response_class=HTMLResponse)
def stop_watch(request: Request, job_id: str = Form(...)) -> HTMLResponse:
    watch = get_watch_service()
    watch.stop(job_id)
    return templates.TemplateResponse(
        request, "partials/watch_list.html", {"jobs": watch.list_jobs()}
    )
