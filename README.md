# Train Manager

KTX / SRT 열차 **좌석 조회 · 예약 · 취소**와 **자동 예약대기(폴링 → 자동 선점 → 결제 알림)** 기능을 제공하는 웹 서비스.

> KIRO 연습용 프로젝트. 참조: [NomaDamas/k-skill](https://github.com/NomaDamas/k-skill) 의 `ktx-booking`(korail2-ncard), `srt-booking`(SRTrain) 스킬.

## 특징

- **Mock 우선**: 실제 계정/네트워크 없이 전체 흐름을 구동. `TRAINMGR_DATA_SOURCE=live` 로 실연동 전환.
- **Provider 추상화**: `TrainProvider` 인터페이스 뒤로 KTX(Korail)/SRT 차이를 숨김 → 유지보수·리뷰·확장 용이.
- **자동 예약대기**: 좌석이 없을 때 주기적으로 재조회, 좌석이 나오면 자동 선점 후 결제 안내.
- **자격증명 분리**: 계정 정보를 Google Spreadsheet 등 외부 소스에서 로드(`CredentialStore`).
- **가벼운 UI**: FastAPI + Jinja2 + HTMX (서버 렌더링).

## 요구 사항

- Python **3.10+** (권장 3.12). 실연동 라이브러리(`korail2-ncard`, `SRTrain`)도 3.10+ 필요.

## 빠른 시작 (로컬, Mock 모드)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
# http://127.0.0.1:8000 접속
```

Mock 모드에서는 데모 계정(`데모 KTX 계정`, `데모 SRT 계정`)이 자동 제공되며 실제 예약은 발생하지 않습니다.

### 테스트

```bash
pytest
```

## Docker

```bash
docker build -t train-manager .
docker run --rm -p 8000:8000 train-manager
```

## 설정 (환경변수)

모든 키는 `TRAINMGR_` 접두사를 사용합니다. `.env.example` 참고.

| 키 | 기본값 | 설명 |
|---|---|---|
| `TRAINMGR_DATA_SOURCE` | `mock` | `mock`(가짜) 또는 `live`(실제 Korail/SRT) |
| `TRAINMGR_SESSION_SECRET` | dev용 | 운영 시 랜덤 값으로 교체 |
| `TRAINMGR_WATCH_POLL_INTERVAL_SEC` | `30` | 자동대기 폴링 주기(초) |
| `TRAINMGR_WATCH_MAX_DURATION_SEC` | `1800` | 최대 감시 시간(초) |
| `TRAINMGR_WATCH_MAX_JOBS` | `5` | 동시 감시 개수 |
| `TRAINMGR_CREDENTIAL_SOURCE` | `disabled` | `disabled`(Mock 계정) / `service_account` / `csv_url` |
| `TRAINMGR_GOOGLE_SERVICE_ACCOUNT_FILE` | - | 서비스 계정 JSON 경로 |
| `TRAINMGR_GOOGLE_SPREADSHEET_ID` | - | 스프레드시트 ID |
| `TRAINMGR_GOOGLE_WORKSHEET_NAME` | `credentials` | 워크시트(탭) 이름 |
| `TRAINMGR_GOOGLE_CSV_URL` | - | `csv_url` 방식일 때 CSV export URL |

### Google Spreadsheet 자격증명

기대 컬럼(대소문자 무시, 순서 무관):

| provider | login_id | password | ncard_no | label |
|---|---|---|---|---|
| ktx | myid | mypw | (선택) | 내 코레일 |
| srt | myid | mypw | | 내 SRT |

- `service_account`: 비공개 시트 + 서비스 계정 JSON (권장). 시트를 서비스 계정 이메일과 공유해야 함.
- `csv_url`: 시트를 "링크가 있는 사용자 보기"로 공개 후 CSV export URL 사용 (인증 불필요, URL 노출 주의).

## 프로젝트 구조

```
app/
├── main.py              # FastAPI 진입점
├── config.py            # 설정 (pydantic-settings)
├── web.py               # Jinja2 템플릿/필터
├── api/routes.py        # HTTP 라우터 (HTMX 부분 렌더링)
├── schemas/             # Pydantic 도메인 모델/DTO
├── providers/           # 열차사 어댑터
│   ├── base.py          # TrainProvider 인터페이스
│   ├── mock.py          # 가짜 데이터
│   ├── ktx.py / srt.py  # 실연동 스텁 (korail2-ncard / SRTrain)
│   └── factory.py       # data_source 에 따라 provider 선택
├── credentials/         # 자격증명 소스
│   ├── base.py
│   ├── mock_store.py
│   ├── google_sheet_store.py
│   └── factory.py
├── services/            # 비즈니스 로직
│   ├── booking.py       # 조회/예약/취소
│   └── watch.py         # 자동 예약대기(폴링)
├── templates/           # Jinja2 + HTMX 화면
└── static/app.css
```

## 실연동(live) 전환 시 할 일

1. `pip install korail2-ncard SRTrain pycryptodome`
2. `app/providers/ktx.py`, `app/providers/srt.py` 의 메서드 구현 (search/seats/reserve/list_reservations/cancel)
3. `TRAINMGR_DATA_SOURCE=live`, `TRAINMGR_CREDENTIAL_SOURCE=service_account`(또는 `csv_url`) 설정

## 주의사항

- 실제 Korail/SRT 자동화는 각 사의 약관/anti-bot 정책 영향을 받습니다. **개인 학습/개인 용도** 전제로 사용하세요.
- `reserve` 는 실제 좌석을 선점합니다. **결제는 공식 화면에서** 진행해야 합니다(본 서비스는 결제를 자동화하지 않음).
- 자격증명은 로그/화면에 마스킹되며, 무료 해외 호스팅은 IP 차단·보안 이슈로 비권장입니다(로컬/국내 VPS 권장).

## 결정 로그

설계 결정 사항은 [`docs/decisions.md`](docs/decisions.md) 에서 관리합니다.
