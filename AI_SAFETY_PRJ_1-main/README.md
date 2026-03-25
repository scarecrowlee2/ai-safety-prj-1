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
- Dev Mock Receiver (개발/테스트 전용): `POST/GET/DELETE /api/v1/dev/mock-receiver/events`
- Dev Mock Diagnostics (개발/테스트 전용): `GET /api/v1/dev/mock-receiver/diagnostics`

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

## 10) 개발/로컬 연동 검증용 Mock Receiver (MVP 4차)

- `Spring Boot`를 수정할 수 없는 개발 단계에서 Python notifier outbound payload를 end-to-end로 검증하기 위한 **개발/테스트 전용 수신기**입니다.
- 목적은 실제 운영 기능 대체가 아니라, Python 전송 경로(업로드 분석 / realtime / outbox retry) 검증입니다.
- 노출 제어:
  - `DEV_MOCK_RECEIVER_ENABLED=true`일 때만 라우트 포함됩니다.
  - 운영 환경(`APP_ENV=prod`)에서는 `DEV_MOCK_RECEIVER_ENABLED=false`를 권장합니다.
- 주요 경로:
  - `POST /api/v1/dev/mock-receiver/events`: outbound payload 수신/기록
  - `GET /api/v1/dev/mock-receiver/events`: 최근 수신 payload 조회
  - `DELETE /api/v1/dev/mock-receiver/events`: 기록 초기화
  - `GET /api/v1/dev/mock-receiver/diagnostics`: mock 수신 건수 + notifier 마지막 시도 + outbox 건수

### 로컬 E2E 검증 절차(권장)

1. 서버 실행
   - `uvicorn app.main:app --reload`
2. `.env` 설정
   - `SPRING_BOOT_EVENT_URL=http://127.0.0.1:8000/api/v1/dev/mock-receiver/events`
   - `SPRING_BOOT_DELIVERY_ENABLED=true`
   - realtime 검증 시 `REALTIME_NOTIFY_ENABLED=true`, `REALTIME_NOTIFY_EVENT_TYPES=fall,inactive`, `REALTIME_NOTIFY_RESIDENT_ID=<id>`
3. 업로드 분석 전송 검증
   - `POST /api/v1/analyze/video` + `notify=true` 호출
   - `GET /api/v1/dev/mock-receiver/events`에서 payload 수신 확인
4. realtime 전송 검증
   - realtime 이벤트(FALL/INACTIVE) 발생 후 mock receiver 수신 확인
   - MVP 기준 `VIOLENCE`는 외부 outbound로 전송되지 않음
5. 실패/재시도 검증
   - `SPRING_BOOT_EVENT_URL`을 일시적으로 잘못 설정하거나 수신 불가 상태를 만들고 이벤트 전송
   - `GET /api/v1/dev/mock-receiver/diagnostics`에서 outbox 적재 건수 확인
   - URL 복구 후 `POST /api/v1/retry-outbox` 실행
   - `GET /api/v1/dev/mock-receiver/events`에서 재수신 확인

### realtime outbound 현재 전제/한계

- outbound 대상 이벤트: `FALL`, `INACTIVE` (MVP 기준)
- `resident_id`는 현재 `REALTIME_NOTIFY_RESIDENT_ID` 단일 고정 매핑
- `snapshot_path`는 realtime snapshot 저장 성공 시 실제 파일 경로, 실패 시 `realtime://stream` fallback
