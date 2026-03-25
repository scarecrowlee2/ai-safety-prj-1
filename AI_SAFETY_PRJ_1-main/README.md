# AI Smart Safety MVP (Official FastAPI App)

이 디렉터리(`AI_SAFETY_PRJ_1-main/`)가 현재 코드 기준 공식 실행 루트입니다.

- 공식 앱 루트: `AI_SAFETY_PRJ_1-main/`
- 공식 FastAPI 엔트리포인트: `app.main:app`
- 개발 실행 명령: `uvicorn app.main:app --reload`

---

## 1) 빠른 시작

아래 명령은 모두 `AI_SAFETY_PRJ_1-main/`에서 실행합니다.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

`ENABLE_YOLO_PERSON_GATE=true`로 운영할 경우(권장) optional 의존성도 설치하세요.

```bash
pip install -r requirements-optional.txt
```

## 2) 접속 경로(현재 코드 기준)

- API docs: `GET /docs`
- Health/Diagnostics: `GET /api/v1/health`
- Realtime 대시보드 UI: `GET /realtime`
- Realtime 점검용 MJPEG 스트림: `GET /realtime/video`
- Realtime 이벤트 목록 API: `GET /api/v1/realtime/events`
- Realtime 상태 요약 API: `GET /api/v1/realtime/status`
- 업로드 분석 API: `POST /api/v1/analyze/video`
- Outbox 재전송: `POST /api/v1/retry-outbox`

## 3) 기능 범위 구분 (업로드 vs 실시간)

### 업로드 분석기 (`POST /api/v1/analyze/video`)

- 현재 지원 detector: `fall`, `inactive`
- 현재 미지원 detector: `violence` (실시간 파이프라인 전용)
- 요청 형식: `multipart/form-data`
  - `resident_id` (int, 필수)
  - `video` (file, 필수)
  - `notify` (bool, 선택)

### 실시간 감지 (대시보드/스트림)

- 대상 경로: `/realtime`, `/realtime/video`, `/api/v1/realtime/events`, `/api/v1/realtime/status`
- 실시간 파이프라인 detector 범위: `fall`, `inactive`, `violence`

## 4) Realtime 경로 역할

- `/realtime`: 운영 대시보드 페이지(상태 배지, 이벤트 패널, 영상 패널)
- `/realtime/video`: 대시보드가 소비하는 MJPEG 프레임 스트림(점검 시 직접 호출 가능)
- `/api/v1/realtime/events`: 최근 이벤트 리스트(JSON) 조회
- `/api/v1/realtime/status`: 최근 이벤트 기반 상태 요약(JSON, 예: `fall/inactive/violence/state`)

## 5) Inactive detector 운영 주의사항

- 운영에서 inactive를 신뢰성 있게 쓰려면 `ENABLE_YOLO_PERSON_GATE=true`를 권장합니다.
- gate 비활성(`false`)이면 inactive detector가 `degraded`(제한 모드)로 동작할 수 있습니다.
- `ENABLE_YOLO_PERSON_GATE=true`인데 YOLO person gate 준비가 실패하면 시작 시 fail-fast 될 수 있습니다.
- 점검 시 `GET /api/v1/health`의 `detectors.inactive`에서 아래를 확인하세요.
  - `mode` (`full` / `degraded` / `disabled` / `error`)
  - `person_gate_enabled`
  - `person_gate_backend`
  - `person_gate_ready`

## 6) Health/Diagnostics에서 확인할 수 있는 것

`GET /api/v1/health`는 현재 코드 기준으로 다음을 빠르게 확인하는 용도입니다.

- 서비스 상태(`status`: `ok` 또는 `degraded`)
- 업로드 분석 지원/미지원 detector 목록
- detector별 상태(`detectors.fall`, `detectors.inactive`, `detectors.violence`)
- 경고 목록(`warnings`)

## 7) 참고

- 웹캠 미연결/오류 환경에서는 `/realtime/video`가 실영상 대신 fallback 상태 프레임을 반환할 수 있습니다.
- 레거시 실행 경로(`uvicorn app.api.stream:app`)는 현재 공식 경로가 아닙니다.


## 8) Python 감지 서버의 외부 연동(MVP 1차)

- 이 프로젝트는 **감지 서버(Python/FastAPI)** 역할을 담당하며, 외부 업무 상태 관리는 Spring Boot가 담당합니다.
- 외부 전송(outbound) 이벤트는 MVP 기준으로 `FALL`, `INACTIVE`만 허용됩니다.
- `VIOLENCE`는 실시간 UI/로그/분석 등 **내부 파이프라인에는 유지**될 수 있지만 외부 전송 대상은 아닙니다.
- outbound payload의 `status` 기본값은 항상 `PENDING`으로 고정되며, `CONFIRMED`/`CLOSED` 전이는 Spring Boot 책임입니다.
- 실시간 경로에서도 outbound notifier 경로를 통해 전송 가능하며, 대상 이벤트는 MVP 기준 `FALL`, `INACTIVE`입니다.
- realtime outbound 이벤트는 발생 순간 프레임을 `REALTIME_SNAPSHOT_DIR`에 저장하고 해당 실제 파일 경로를 `snapshot_path`로 사용합니다(저장 실패 시 `realtime://stream` fallback).
- realtime outbound의 `resident_id`는 현재 단일 설정값(`REALTIME_NOTIFY_RESIDENT_ID`) 고정 매핑 방식입니다.

## 9) Notifier / Outbox 동작 (MVP 2차)

- Python(FastAPI) 감지 서버는 outbound payload를 Spring Boot로 전송하고, 전송 불가/실패 시 outbox(JSONL)에 큐잉합니다.
- outbox는 공식 이벤트 저장소(SQLite)를 대체하지 않으며, **전달 보조 수단**입니다.
- outbox 레코드에는 `payload`, `queued_at`, `reason`, `source`, `last_error`가 저장됩니다.
- 재전송은 API `POST /api/v1/retry-outbox` 또는 notifier의 retry 경로로 수행할 수 있으며, 성공 항목은 outbox에서 제거되고 실패 항목은 유지됩니다.
