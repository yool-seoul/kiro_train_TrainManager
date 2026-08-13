# 대화 감사 로그 (Audit Log)

> 이 문서는 본 프로젝트에 대한 사용자–AI(Kiro) 대화 및 수행 작업의 감사 기록입니다.
> 정책: **앞으로의 모든 대화도 이 파일에 턴 단위로 계속 누적 기록**합니다.
> 형식: 각 턴마다 `사용자 요청 요약` + `AI 수행/응답 요약`을 남깁니다. (민감정보/시크릿 값은 기록하지 않음)

---

## Turn 1 — 프로젝트 요구사항 제시
**사용자**: KTX/SRT 열차 좌석 조회·예약 웹 서비스 제작 요청. 참조 레포 `https://github.com/NomaDamas/k-skill` 활용. 파이썬 개발자가 유지보수/리뷰하기 좋은 구조. 무료 웹 호스팅 우선 검토, 아니면 로컬호스트. 확정 필요 사항은 대화로 결정.

**AI**:
- 참조 레포 조사 결과 = AI 에이전트용 "스킬 가이드" 모음이며, 실제 예매는 하위 파이썬 라이브러리가 담당함을 확인.
  - KTX/Korail → `korail2-ncard` (+ `pycryptodome`), anti-bot(Dynapath) 우회 필요
  - SRT → `SRTrain`
- 핵심 제약 정리: 실제 계정/실제 예약 필요, 자격증명 민감, 무료 해외 호스팅 부적합 가능성(anti-bot IP 차단·아웃바운드 제한·보안), 약관/합법성.
- 제안 구조(FastAPI+Pydantic, TrainProvider 어댑터로 KTX/SRT 추상화, Jinja2/HTMX) 및 확인 필요 항목 제시.

## Turn 2 — 결정사항 문서화 요청
**사용자**: 확정 필요 사항을 별도 문서로 관리. 문서에 답변하겠음.

**AI**: `docs/decisions.md` 생성. D1~D6 결정 항목(옵션/추천/답변 칸), 배경 요약, 핵심 제약, 제안 구조 포함.

## Turn 3 — 결정 답변 완료
**사용자**: 답변 완료. (D1=a 전체기능, D2=b Mock 우선, D3=Google Spreadsheet에서 자격증명 읽기, D4=a 로컬+Docker, D5=a Jinja2/HTMX, D6=a FastAPI+Pydantic, 추가: 좌석 없으면 폴링→선점→결제알림)

**AI**:
- 해석: 전체 기능을 Mock provider 위에서 먼저 완성 후 실 provider 스위치.
- `docs/decisions.md`에 후속 항목 D7(Google Sheet 연동 세부), D8(자동 예약대기 세부) 추가.
- 8단계 작업 계획 수립 후 구현 시작:
  1. requirements.txt, `app/config.py`(Settings, env_prefix=TRAINMGR_, data_source mock|live), `.env.example`, `app/__init__.py`
  2. `app/schemas/train.py` (TrainType, SeatClass, ReservationStatus, WatchStatus, Passengers, Credential, SeatDetail, CarSeats, TrainOption, Reservation, WatchJob)
  3. `app/providers/` (base TrainProvider ABC, mock, ktx/srt 실연동 스텁, factory)
  4. `app/credentials/` (base, mock_store, google_sheet_store[service_account/csv_url], factory)
  5. `app/services/` (booking: 조회/예약/취소, watch: 폴링 자동선점)
  6. `app/api/routes.py` + `app/web.py` + 템플릿(base/index/results/seats/reservation/watch 등) + `static/app.css`
  7. Dockerfile, .dockerignore, .gitignore, tests/test_app.py, README.md
- 검증: 시스템 Python 3.9는 `str|None` 문법 미지원 → conda Python 3.13으로 venv 구성. pytest 4건 통과, uvicorn 실서버로 주요 엔드포인트 200 확인.

## Turn 4 — 커밋 & 푸시 (main)
**사용자**: 현재까지 작업 commit 후 GitHub push. 커밋 유저 = Luke Skywalker <sangyool.skt@gmail.com>.

**AI**: 전역 git config 미변경(`-c` 옵션 사용)으로 커밋. 시크릿 파일 미포함 확인. `main`에 push 완료(origin/main = 로컬 HEAD 동기화). osxkeychain 지연 이슈는 store 헬퍼로 확인.

## Turn 5 — 유저 테스트용 서버 기동
**사용자**: 유저 테스트용으로 웹 띄우기.

**AI**: `uvicorn`을 백그라운드로 http://127.0.0.1:8000 기동. 화면 구성 및 Mock 모드 테스트 팁 안내.

## Turn 6 — 두 버튼 차이 설명
**사용자**: '이 조건으로 자동 예약대기 등록' 버튼과 '예약' 버튼 차이 설명.

**AI**: 예약=즉시 1회 특정 열차 선점(매진 시 에러), 자동 예약대기=조건에 맞는 가장 이른 열차를 주기 폴링하며 좌석 생기면 자동 선점. 비교표 제공. 매진 열차 예약 버튼 비활성화 + 개별 대기 옵션을 제안.

## Turn 7 — 매진 예약 비활성화 + 대기 버튼 추가
**사용자**: 매진 열차는 예약 버튼 비활성화, '대기' 버튼 추가.

**AI**:
- `WatchJob`에 `target_train_id`/`target_train_name` 추가, `WatchService._pick`이 특정 열차 지정 지원.
- `/watch` 라우트에 target 파라미터 추가.
- Mock: 매진 열차가 최초 조회 후 5~30초 뒤 좌석 풀리도록(release schedule) 변경, 열차 목록/ID deterministic 유지.
- `results.html`: 전 좌석 매진 시 예약 버튼 disable + 개별 '대기' 버튼, 좌석등급 옵션 매진 시 disable. 실시간 갱신되는 `watch_panel.html` 추가.
- pytest 5건 통과, 실서버 확인(매진 4건 대기 버튼/비활성화/watch 패널 정상).

## Turn 8 — 예약 완료 후 대기 취소 불가 + 상태 라벨
**사용자**: reserved 후 대기 취소 불가, 상태값 'end waiting' 식으로 반영.

**AI**:
- `WatchJob.is_active`(watching만 true), `status_label`(reserved/stopped/expired/failed에 'end waiting' 명시) 추가.
- `watch_list.html`: 중단 버튼은 active일 때만, 이후 '—' 표시. `WatchService.stop`에 non-watching이면 상태 미변경 서버 가드.
- pytest 6건 통과, 실서버 확인(reserved 시 'end waiting' 라벨, 중단 버튼 미노출).

## Turn 9 — 별도 브랜치 커밋 & 푸시
**사용자**: 커밋 승인, 단 작업 내용을 반영한 간단한 이름의 별도 브랜치로.

**AI**: `feature/watch-soldout-ux` 브랜치 생성, 커밋(작성자 Luke Skywalker), origin에 push + 업스트림 설정.

## Turn 10 — PR 생성
**사용자**: PR 생성.

**AI**: gh CLI 부재 → 저장된 git 자격증명 토큰으로 GitHub REST API 호출(토큰 값 미노출). **PR #1** 생성: https://github.com/yool-seoul/kiro_train_TrainManager/pull/1 (main ← feature/watch-soldout-ux).

## Turn 11 — 감사 로그 생성
**사용자**: 지금까지의 모든 대화를 `audit.md`로 만들고 관리. 앞으로의 모든 대화도 audit.md에 보관.

**AI**: 저장소 루트에 `audit.md` 생성(본 문서). 이후 모든 턴을 이 파일에 계속 누적 기록하기로 함.

## Turn 12 — 감사 로그 main 커밋 & 푸시
**사용자**: `audit.md`(및 감사 로깅 steering)를 main 브랜치로 바로 커밋하고 푸시.

**AI**: `audit.md`, `.kiro/steering/audit-logging.md`를 `main` 으로 전환 후 커밋(작성자 Luke Skywalker)하고 origin/main 에 push.
