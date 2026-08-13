# 프로젝트 결정 사항 (Decision Log)

> KTX / SRT 좌석 조회 및 예약 웹 서비스
>
> 사용법: 각 항목의 **[답변]** 칸에 원하는 선택지(또는 자유 의견)를 적어주세요.
> 답변이 채워지면 그 내용을 기준으로 구현을 진행합니다. 미정 항목은 `추천` 값을 임시 기본값으로 사용합니다.

---

## 배경 요약

- 참조 레포 `NomaDamas/k-skill` 은 파이썬 라이브러리가 아니라 **AI 에이전트용 스킬 가이드 모음**이다.
- 실제 예매는 그 아래 파이썬 라이브러리가 담당한다.
  - **KTX/Korail** → `korail2-ncard` (+ `pycryptodome`)
    - 원본 `korail2` 는 Korail anti-bot(Dynapath) 때문에 `MACRO ERROR` 가 날 수 있고, k-skill 헬퍼가 토큰을 붙여 우회한다.
  - **SRT** → `SRTrain` (`import SRT`)
- 두 라이브러리 모두 **실제 계정 로그인 / 실제 좌석 예약**을 수행한다. (결제는 별도 handoff)

---

## 핵심 제약 (참고용, 결정에 영향)

1. 실제 Korail/SRT 계정과 실제 예약이 필요하다. `reserve` 는 진짜 좌석을 선점한다.
2. 사용자 ID/PW 를 다뤄야 하므로 자격증명 처리 방식이 민감하다.
3. 무료 해외 호스팅은 anti-bot 해외 IP 차단, 아웃바운드 제한(PythonAnywhere 등), 보안 문제로 부적합 가능성이 크다.
4. Korail/SRT 자동화는 약관 위반 소지 및 anti-bot 차단 위험이 있다. 개인 학습/개인 용도 전제를 권장.

---

## 결정 항목

### D1. 기능 범위 / 진행 순서

- (a) 처음부터 조회 + 예약 + 취소 전체 구현
- (b) **단계적**: ① 좌석 조회 먼저 → ② 예약 → ③ 취소 순으로 확장 *(조회만도 로그인 필요)*

- 추천: **(b) 단계적**
- [답변]: a

---

### D2. 실계정 연동 vs Mock 데이터

- (a) 처음부터 진짜 Korail/SRT 계정으로 실제 동작
- (b) **Mock(가짜) 데이터로 UI/구조부터** 만들고 실연동은 나중에 스위치로 붙이기

- 추천: **(b) Mock 우선** (학습·리뷰 목적에 적합, 실 예약 사고 방지)
- [답변]: b

---

### D3. 자격증명(ID/PW) 처리 방식

- (a) 사용자가 화면에서 입력 → **세션/메모리에만 보관, 디스크 저장 안 함**
- (b) 서버 `.env` 에 본인 계정 1개만 넣고 개인용으로 사용
- (c) 암호화하여 DB/파일에 저장 (다중 사용자 지속 로그인)

- 추천: **(a) 세션 메모리 only** (Mock 단계에서는 입력 없이도 동작)
- [답변]: ID/PW는 별도의 google spreadsheet 로 관리함. 여기서 읽어로도록 구현 필요.

---

### D4. 호스팅 방식

- (a) **로컬호스트 우선 + Docker 패키징** (나중에 국내 VPS 등으로 이전 가능)
- (b) 특정 무료 호스팅을 지정해서 시도 (서비스명 기입)

- 추천: **(a) 로컬 + Docker**
- [답변]: a

---

### D5. 프런트엔드 형태

- (a) **서버 렌더링**: FastAPI + Jinja2 / HTMX (가볍고 리뷰 쉬움)
- (b) 분리형 SPA: React 등 (프런트/백 분리)

- 추천: **(a) Jinja2 / HTMX**
- [답변]: a

---

### D6. 백엔드 스택 (참고 확인)

- 제안: **FastAPI + Pydantic**, 열차사별 `TrainProvider` 어댑터로 KTX/SRT 추상화
- 다른 선호(Flask, Django 등) 있으면 기입

- 추천: **FastAPI + Pydantic**
- [답변]: a

---

## 제안 디렉터리 구조 (참고)

```
train-manager/
├── app/
│   ├── main.py                 # FastAPI 진입점
│   ├── config.py               # 설정(환경변수)
│   ├── api/                    # 라우터 (HTTP 레이어)
│   ├── providers/              # 열차사별 어댑터
│   │   ├── base.py             # TrainProvider 추상 인터페이스
│   │   ├── ktx.py              # korail2-ncard 감쌈
│   │   └── srt.py              # SRTrain 감쌈
│   ├── schemas/                # Pydantic DTO
│   ├── services/               # 비즈니스 로직
│   └── templates/              # Jinja2 / HTMX 화면
├── tests/
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 추가 논의 / 미해결 질문 (자유 기입)

- 좌석이 없을 경우는 계속 조회하여 새로운 좌석이 생겼을 경우 일단 좌석을 선점하고 유저에게 결제를 하라고 알려줄 수 있어야 함.

---

## 후속 결정 항목 (1차 답변 이후 추가)

> D1~D6 답변 결과: **전체 기능(조회+예약+취소)을 Mock provider 위에서 먼저 완성 → 이후 실 provider 로 스위치**.
> 아래 D7, D8 은 새로 추가된 요구사항(Google Sheet 자격증명, 자동 예약대기)의 세부 사항입니다. **[답변]** 칸에 적어주세요.
> (미정이면 `추천/기본값`으로 골격을 먼저 만들고, 답변 주시면 반영합니다.)

### D7. Google Spreadsheet 자격증명 연동 방식

- **D7-1. 접근(인증) 방식**
  - (a) **서비스 계정(Service Account) JSON + gspread** — 비공개 시트, 보안상 권장
  - (b) 시트를 "링크가 있는 모든 사용자 보기"로 공개 후 **CSV export URL** 로 읽기 (인증 불필요, 간단하지만 URL 노출 시 누구나 열람)
  - (c) OAuth 사용자 인증
  - 추천: **(a) 서비스 계정**
  - [답변]: (a) 서비스 계정(Service Account) JSON + gspread — 비공개 시트 유지, 보안 권장. 상세 구조는 하단 "부록 A" 참조. a

- **D7-2. 시트 컬럼 스키마** (기본 제안)
  - 컬럼: `provider`(ktx/srt), `login_id`, `password`, `ncard_no`(선택), `label`(선택, 사용자 구분용)
  - 다르게 원하시면 실제 컬럼 구성을 적어주세요.
  - [답변]: 제안대로 진행

- **D7-3. 스프레드시트 지정 값**
  - 필요한 값: 스프레드시트 ID(또는 URL), 워크시트(탭) 이름
  - 서비스 계정 방식이면: 서비스 계정 JSON 키 파일 경로(환경변수로 주입)
  - *실제 비밀 값은 문서에 적지 말고, "이런 방식으로 주입하겠다"만 확인해 주세요.*
  - [답변]: 서비스 계정 방식 제공
  - 시트에 여러 계정이 있을 때 웹에서 (a) 드롭다운으로 `label` 선택 / (b) provider 별 첫 행 자동 사용
  - 추천: **(a) label 드롭다운 선택**
  - [답변]: a

---

### D8. 자동 예약대기(폴링) 동작

- **D8-1. 알림(선점 성공) 전달 방식**
  - (a) **웹 UI 내 알림** (watch job 목록에 상태 표시 + 브라우저 알림/SSE)
  - (b) 이메일
  - (c) 카카오톡/텔레그램 등 메신저
  - 추천: **(a) 웹 UI 내 알림** (Mock 단계에 적합, 이후 확장)
  - [답변]:c

- **D8-2. 폴링 주기**
  - anti-bot/계정 보호 위해 보수적으로. 제안: 기본 **30초** (최소 15초 제한)
  - [답변]: 10초

- **D8-3. 좌석 발견 시 동작**
  - (a) **자동 선점(reserve)** 후 "결제 필요" 상태로 알림  ← 요구사항과 일치
  - (b) 선점하지 않고 알림만
  - 추천: **(a) 자동 선점 + 결제 알림**
  - [답변]: a

- **D8-4. 안전장치**
  - 최대 감시 시간(예: 30분 후 자동 종료), 동시 watch 개수 제한(예: 5개) — 값 조정 원하면 기입
  - [답변]: 30분 후 자동 종료 및 동시 watch 수 5개

---

## 부록 A. 서비스 계정(Service Account) JSON + gspread 구조

> D7-1 (a) 선택에 대한 상세 설명. 현재 `app/credentials/google_sheet_store.py` 의
> `GoogleSheetCredentialStore._read_via_gspread()` 에 이미 구현되어 있다.

### A-1. 전체 그림

```
[Google Cloud]                    [로컬/서버]                      [Google Sheets]
서비스 계정 생성  ──JSON 키 발급──▶  service_account.json  ──인증──▶  시트에 계정 이메일 공유
   (봇 계정)                         (gspread가 읽음)                  (열람 권한 부여)
```

핵심은 **사람 계정으로 로그인하지 않고, 앱 전용 로봇 계정(서비스 계정)이 JSON 키로 인증해
특정 시트만 읽는다**는 점이다. 시트를 인터넷에 공개할 필요가 없어 보안상 권장된다.

### A-2. 서비스 계정이란

- 사람이 아니라 **애플리케이션이 쓰는 구글 계정**. `something@your-project.iam.gserviceaccount.com` 형태.
- 비밀번호 대신 **JSON 키 파일**로 인증한다. JSON 안에는 `private_key`(RSA 개인키),
  `client_email`, `token_uri` 등이 들어 있다.
- 이 개인키로 JWT를 서명해 구글 OAuth 서버에서 짧은 수명의 access token을 받아 API를 호출한다.
  (gspread가 내부적으로 처리)

### A-3. 셋업 절차 (한 번만)

1. Google Cloud Console에서 프로젝트 생성
2. **Google Sheets API** 와 **Google Drive API** 활성화 (gspread가 시트를 열 때 Drive API도 사용)
3. 서비스 계정 생성 → 키 발급 → `service_account.json` 다운로드
4. 대상 스프레드시트의 "공유"에서 서비스 계정 이메일(`...iam.gserviceaccount.com`)을
   **뷰어(읽기)** 권한으로 추가
   - 이 단계가 핵심. 시트를 공개하지 않고 로봇 계정 하나에게만 접근을 허용한다.
   - 이 공유를 빠뜨리면 권한 없음(APIError)이 발생한다. 가장 흔한 실수.

### A-4. 코드 동작 (`_read_via_gspread`)

```python
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",  # 시트 읽기 전용
    "https://www.googleapis.com/auth/drive.readonly",         # 파일 열기용
]

# 1) JSON 키 파일로 자격증명 생성 (scope 최소 권한: readonly)
creds = SACredentials.from_service_account_file(path, scopes=_SCOPES)
# 2) gspread 클라이언트 인증
client = gspread.authorize(creds)
# 3) 스프레드시트 ID로 열기 (URL의 /d/<ID>/ 부분)
sheet = client.open_by_key(spreadsheet_id)
# 4) 워크시트(탭) 선택
worksheet = sheet.worksheet(worksheet_name)
# 5) 첫 행을 헤더로 해서 [{col: value}, ...] 반환
return worksheet.get_all_records()
```

설계 포인트:

- **최소 권한 원칙**: scope를 `readonly`로 제한 → JSON 키가 유출돼도 시트 수정/삭제 불가.
- **지연 import**: `import gspread` 를 함수 안에서 수행 → `disabled`/`csv_url` 모드에서는
  무거운 의존성 설치 불필요.

반환된 각 행은 `_row_to_credential()` 에서 정규화된다. 컬럼명을 소문자·trim 처리하여
대소문자/공백에 관대하고, 필수 컬럼(`provider`, `login_id`, `password`)이 비면 빈 행으로 보고 건너뛴다.

### A-5. 시트 구조 (기대 컬럼)

첫 행이 헤더여야 하며, 컬럼 순서·대소문자는 무관하다.

| provider | login_id | password | ncard_no | label |
|----------|----------|----------|----------|-------|
| ktx | myid1 | pw1 | 1234 | 본인 |
| srt | myid2 | pw2 | | 가족 |

- `provider` — `ktx` 또는 `srt` 만 허용 (다른 값이면 `CredentialError`)
- `login_id`, `password` — 필수
- `ncard_no`, `label` — 선택 (`label` 은 여러 계정을 구분하는 이름)

### A-6. 설정 (.env)

`app/config.py` 의 `Settings` 가 `TRAINMGR_` 접두사로 환경변수를 읽는다.

```bash
TRAINMGR_CREDENTIAL_SOURCE=service_account
TRAINMGR_GOOGLE_SERVICE_ACCOUNT_FILE=./secrets/service_account.json
TRAINMGR_GOOGLE_SPREADSHEET_ID=1AbcD...xyz     # 시트 URL의 /d/ 뒤 ID
TRAINMGR_GOOGLE_WORKSHEET_NAME=credentials     # 탭 이름 (기본값 credentials)
```

`factory.py` 의 `get_credential_store()` 가 `credential_source` 값을 보고 store를 고른다.
`disabled` 면 `MockCredentialStore`(데모 계정), 그 외엔 `GoogleSheetCredentialStore`.

### A-7. service_account vs csv_url 비교

| 항목 | service_account (권장) | csv_url |
|------|------------------------|---------|
| 시트 공개 여부 | 비공개 유지 | "링크가 있는 모든 사용자" 공개 필요 |
| 인증 | JSON 키로 로봇 계정 인증 | 인증 없음 |
| 의존성 | `gspread`, `google-auth` 설치 필요 | 없음 (표준 `urllib`, `csv`) |
| 보안 | 높음 (비밀번호 담긴 시트에 적합) | 낮음 (URL 아는 누구나 열람) |
| 설정 난이도 | 다소 복잡 (Cloud 콘솔 셋업) | 간단 |

계정 비밀번호처럼 민감 정보가 들어가므로 시트를 공개하지 않는 **service_account 방식이 적합**하다.

### A-8. 운영 시 주의점

- **JSON 키 파일은 절대 커밋 금지.** `./secrets/` 등에 두고 `.gitignore` 에 추가. 유출 시 Cloud 콘솔에서 키 폐기(rotate).
- 매 호출마다 시트를 새로 읽는다(캐시 없음). 계정 변경이 즉시 반영되고, 호출 빈도가 낮아(로그인·예약 시점) 성능 문제는 없다. 트래픽 증가 시 TTL 캐시를 얹으면 된다.
- 시트에 서비스 계정 이메일을 공유하지 않으면 권한 오류가 난다 (A-3 4단계 확인).
