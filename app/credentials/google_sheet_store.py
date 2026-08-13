"""Google Spreadsheet 자격증명 저장소 (D3/D7).

두 가지 접근 방식을 지원한다.
- service_account: gspread + 서비스 계정 JSON (비공개 시트, 권장)
- csv_url:        공개 시트의 CSV export URL (인증 불필요, 간단)

기대 컬럼(대소문자 무시, 순서 무관):
    provider   (ktx | srt)   [필수]
    login_id                  [필수]
    password                  [필수]
    ncard_no                  [선택]
    label                     [선택]

무거운 의존성(gspread/google-auth)은 실제 로드 시점에만 import 한다.
"""

from __future__ import annotations

import csv
import io
import urllib.request

from app.config import Settings
from app.credentials.base import CredentialError, CredentialStore
from app.schemas import Credential, TrainType

_REQUIRED = {"provider", "login_id", "password"}
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _row_to_credential(row: dict[str, str]) -> Credential | None:
    """시트 한 행 → Credential. 필수값 없으면 None (빈 행 스킵)."""
    norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    if not all(norm.get(k) for k in _REQUIRED):
        return None
    try:
        provider = TrainType(norm["provider"].lower())
    except ValueError as exc:
        raise CredentialError(
            f"provider 값이 잘못됨: {norm.get('provider')!r} (ktx|srt 만 허용)"
        ) from exc
    return Credential(
        provider=provider,
        login_id=norm["login_id"],
        password=norm["password"],
        ncard_no=norm.get("ncard_no") or None,
        label=norm.get("label") or None,
    )


class GoogleSheetCredentialStore(CredentialStore):
    """캐시 없이 매 호출마다 시트를 읽는다 (계정 변경 즉시 반영).

    호출 빈도가 높지 않으므로(로그인/예약 시점) 성능 문제는 없다.
    필요 시 TTL 캐시를 추가할 수 있다.
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    # --------------------------------------------------------------- public
    def list_credentials(self, train_type: TrainType | None = None) -> list[Credential]:
        rows = self._read_rows()
        creds: list[Credential] = []
        for row in rows:
            cred = _row_to_credential(row)
            if cred is None:
                continue
            if train_type is None or cred.provider is train_type:
                creds.append(cred)
        return creds

    # -------------------------------------------------------------- private
    def _read_rows(self) -> list[dict[str, str]]:
        source = self._s.credential_source
        if source == "service_account":
            return self._read_via_gspread()
        if source == "csv_url":
            return self._read_via_csv()
        raise CredentialError(
            f"credential_source={source} 는 시트를 읽을 수 없습니다."
        )

    def _read_via_gspread(self) -> list[dict[str, str]]:
        if not self._s.google_service_account_file or not self._s.google_spreadsheet_id:
            raise CredentialError(
                "service_account 방식에는 GOOGLE_SERVICE_ACCOUNT_FILE 와 "
                "GOOGLE_SPREADSHEET_ID 가 필요합니다."
            )
        try:
            import gspread  # type: ignore
            from google.oauth2.service_account import Credentials as SACredentials  # type: ignore
        except ImportError as exc:
            raise CredentialError(
                "gspread/google-auth 미설치. `pip install gspread google-auth` 필요."
            ) from exc

        creds = SACredentials.from_service_account_file(
            self._s.google_service_account_file, scopes=_SCOPES
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(self._s.google_spreadsheet_id)
        worksheet = sheet.worksheet(self._s.google_worksheet_name)
        return worksheet.get_all_records()  # 첫 행을 헤더로 사용

    def _read_via_csv(self) -> list[dict[str, str]]:
        if not self._s.google_csv_url:
            raise CredentialError("csv_url 방식에는 GOOGLE_CSV_URL 이 필요합니다.")
        try:
            with urllib.request.urlopen(self._s.google_csv_url, timeout=10) as resp:  # noqa: S310
                text = resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise CredentialError(f"CSV 시트를 읽지 못했습니다: {exc}") from exc
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)
