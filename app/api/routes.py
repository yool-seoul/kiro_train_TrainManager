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
from app.stations import get_default_stations, get_stations
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


def _render_error(request: Request, message: str, status_code: int = 200) -> HTMLResponse:
    # 기본 200: HTMX 는 비-2xx 응답을 대상 영역에 스왑하지 않으므로,
    # 조각(fragment) 요청의 도메인 오류는 200 으로 반환해 화면에 그대로 노출한다.
    return templates.TemplateResponse(
        request,
        "partials/error.html",
        {"message": message},
        status_code=status_code,
    )


def _notify_reservation_async(reservation) -> None:
    """예약(선점) 성공 알림을 백그라운드로 전송한다.

    - HTTP 응답을 메신저 지연(최대 10초)으로 막지 않도록 daemon 스레드에서 보낸다.
    - 알림 실패가 예약 결과 표시를 깨지 않도록 예외를 삼킨다.
    - notify_channel 이 none 이면 NullNotifier 라 아무 것도 하지 않는다.
    """
    import threading

    def _send() -> None:
        try:
            from app.notify import get_notifier

            get_notifier().notify_reservation(reservation)
        except Exception:  # noqa: BLE001, S110 - 알림 실패는 무시
            pass

    threading.Thread(target=_send, daemon=True).start()


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
    train_types = list(TrainType)
    default_type = train_types[0] if train_types else None
    try:
        # 초기 노출 계정은 기본 선택 열차(첫 번째 종류)의 계정만.
        creds = store.list_credentials(default_type) if default_type else []
    except Exception:  # noqa: BLE001 - 자격증명 로드 실패 시에도 화면은 뜨게
        creds = []
    default_date, default_time = _default_datetime()
    default_dep, default_arr = get_default_stations(default_type) if default_type else ("서울", "부산")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "settings": settings,
            "credentials": creds,
            "train_types": train_types,
            "default_date": default_date,
            "default_time": default_time,
            "stations": get_stations(default_type) if default_type else [],
            "default_dep": default_dep,
            "default_arr": default_arr,
            "nav_active": "search",
        },
    )


@router.get("/accounts", response_class=HTMLResponse)
def accounts(request: Request, train_type: TrainType) -> HTMLResponse:
    """선택한 열차 종류(provider)에 해당하는 계정 옵션만 반환 (계정 드롭다운 갱신용)."""
    store = get_credential_store()
    try:
        creds = store.list_credentials(train_type)
    except Exception:  # noqa: BLE001
        creds = []
    return templates.TemplateResponse(
        request, "partials/account_options.html", {"credentials": creds}
    )


@router.get("/stations", response_class=HTMLResponse)
def stations(request: Request, train_type: TrainType) -> HTMLResponse:
    """선택한 열차 종류에 해당하는 역 옵션을 반환 (출발/도착역 드롭다운 갱신용)."""
    station_list = get_stations(train_type)
    default_dep, default_arr = get_default_stations(train_type)
    return templates.TemplateResponse(
        request, "partials/station_options.html",
        {"stations": station_list, "default_dep": default_dep, "default_arr": default_arr},
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
            "nav_active": "credentials",
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
        request, "reservations.html", {"reservations": items, "nav_active": "reservations"}
    )


@router.get("/watch", response_class=HTMLResponse)
def watch_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "watch.html", {"jobs": get_watch_service().list_jobs(), "nav_active": "watch"}
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
    seat_class: str = Form("all"),
    adults: int = Form(1),
    children: int = Form(0),
    seniors: int = Form(0),
    credential_label: str | None = Form(None),
) -> HTMLResponse:
    booking = get_booking_service()
    passengers = _passengers(adults, children, seniors)

    # 좌석 등급 필터: all(모두) | general(일반실) | special(특실)
    seat_filter = seat_class if seat_class in ("all", "general", "special") else "all"
    # 예약/자동대기 기본 좌석 등급(구체값). '모두'면 일반실을 기본으로.
    default_class = SeatClass.SPECIAL if seat_filter == "special" else SeatClass.GENERAL

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
        # HTMX 가 #results 에 그대로 렌더할 수 있도록 200 으로 반환한다.
        return _render_error(request, exc.message, status_code=200)

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "trains": trains,
            "seat_class": default_class,
            "seat_filter": seat_filter,
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
                "seat_class": default_class.value,
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

    _notify_reservation_async(reservation)
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
    job = watch.stop(job_id)
    response = templates.TemplateResponse(
        request, "partials/watch_list.html", {"jobs": watch.list_jobs()}
    )
    # 중단된 job의 target_train_id를 헤더로 전달 → 프론트에서 대기 버튼 re-enable
    if job and job.target_train_id:
        response.headers["HX-Trigger-After-Swap"] = (
            '{"watchStopped":{"trainId":"' + job.target_train_id + '"}}'
        )
    return response
