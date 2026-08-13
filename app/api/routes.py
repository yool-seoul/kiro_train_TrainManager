"""HTTP 라우터.

HTML 페이지 + HTMX 부분 렌더링을 제공한다.
- 서비스/스키마만 의존하고 provider 구체 타입은 모른다.
- 조회 결과의 TrainOption 은 hidden 필드에 JSON 으로 실어 후속 요청(좌석/예약/watch)에 전달한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
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
@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    store = get_credential_store()
    creds = store.list_credentials()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "settings": settings,
            "credentials": creds,
            "train_types": list(TrainType),
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
        )
    except ProviderError as exc:
        return _render_error(request, exc.message)
    return templates.TemplateResponse(
        request, "partials/watch_list.html", {"jobs": watch.list_jobs()}
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
