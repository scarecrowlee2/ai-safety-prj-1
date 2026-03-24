# AI Smart Safety MVP (Official FastAPI App)

이 디렉터리(`AI_SAFETY_PRJ_1-main/`)가 저장소의 **공식 실행/개발 루트**입니다.

- 공식 앱 루트: `AI_SAFETY_PRJ_1-main/`
- 공식 FastAPI 엔트리포인트: `app.main:app`
- 개발 실행 명령: `uvicorn app.main:app --reload`

> 저장소 바깥(outer) 레거시 앱 경로는 더 이상 공식 실행 경로가 아닙니다.

---

## 1) 빠른 시작

아래 명령은 모두 `AI_SAFETY_PRJ_1-main/` 에서 실행합니다.

### Python 가상환경 + 의존성

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

선택(YOLO 사람 감지 게이트 사용 시):

```bash
pip install -r requirements-optional.txt
```

### 환경 파일 준비

```bash
cp .env.example .env
```

### 모델 파일 준비 (fall detector)

낙상 감지는 기본적으로 `./models/pose_landmarker.task` 파일을 사용합니다.

- 기본 경로: `models/pose_landmarker.task`
- 또는 `.env` 에서 `FALL_POSE_TASK_MODEL_PATH` 로 경로 지정

모델 파일이 없으면 서버는 실행되지만, 낙상 감지는 비활성화되고 `/api/v1/health`의 `warnings`/`detectors`에 이유가 표시됩니다.

### 런타임 디렉터리

앱 시작 시 아래 경로들이 자동 생성됩니다.

- `data/`
- `data/snapshots/`
- `data/uploads/`
- `data/outbox/`
- `data/realtime_events.jsonl` 의 상위 디렉터리
- `data/events.db` 의 상위 디렉터리

---

## 2) 개발 서버 실행

```bash
uvicorn app.main:app --reload
```

기본 접속 주소:

- API docs: `http://127.0.0.1:8000/docs`
- root: `http://127.0.0.1:8000/`

---

## 3) 주요 기능 엔드포인트

### Realtime 대시보드/스트림

- Realtime dashboard: `GET /realtime`
- Realtime video stream (MJPEG): `GET /realtime/video`
- Realtime recent events API: `GET /api/v1/realtime/events?limit=6`

### 업로드 분석 API

- Health: `GET /api/v1/health`
- Video analyze(upload): `POST /api/v1/analyze/video`
  - form-data: `resident_id`(int), `video`(file), `notify`(optional bool)
- Outbox 재전송: `POST /api/v1/retry-outbox`

---

## 4) 실행 전/환경 체크 포인트

- 웹캠 realtime 사용 시 카메라 접근 가능해야 합니다.
  - 실패 시 `/realtime/video`는 fallback 상태 프레임을 반환합니다.
- `.env` 주요 변수
  - `APP_TIMEZONE`, `DATA_DIR`, `MODELS_DIR`
  - `FALL_ENABLED`, `FALL_POSE_TASK_MODEL_PATH`
  - `ENABLE_YOLO_PERSON_GATE` (운영에서 inactive 핵심 기능 사용 시 `true` 권장)
  - `YOLO_MODEL` (예: `yolov8n.pt`)
  - `REALTIME_WEBCAM_SOURCE`, `REALTIME_WEBCAM_WIDTH`, `REALTIME_WEBCAM_HEIGHT`, `REALTIME_WEBCAM_FPS`
  - `REALTIME_EVENT_LOG_PATH`, `REALTIME_RECENT_EVENT_LIMIT`
  - `SPRING_BOOT_EVENT_URL` (외부 전송 연동 시)

### Inactive detector 운영 정책

- 운영 환경에서 inactive detector를 핵심 기능으로 사용할 경우 `ENABLE_YOLO_PERSON_GATE=true`를 권장합니다.
- person gate가 비활성화(`false`)면 inactive detector는 제한(degraded) 모드로 동작합니다.
- `ENABLE_YOLO_PERSON_GATE=true`인데 person gate(YOLO)가 준비되지 않으면 앱이 시작 단계에서 fail-fast 합니다.
- 운영 점검 시 `GET /api/v1/health`의 `detectors.inactive`에서 아래를 확인하세요.
  - `person_gate_enabled`
  - `person_gate_backend`
  - `person_gate_ready`
  - `mode` (`full`/`degraded`/`disabled`/`error`)

---

## 5) Smoke Check (시작 후 빠른 검증)

서버 실행 후 아래 순서로 최소 검증을 권장합니다.

1. **앱 기동 확인**
   - `GET /api/v1/health` 가 `200` 응답인지 확인
2. **Realtime 페이지 로드 확인**
   - 브라우저에서 `GET /realtime` 접속
3. **Realtime 스트림 접근 확인**
   - `GET /realtime/video` 호출 시 MJPEG 응답(`multipart/x-mixed-replace`) 확인
4. **Recent events API 확인**
   - `GET /api/v1/realtime/events` 가 JSON payload 반환하는지 확인
5. **Upload 분석 API 확인**
   - `POST /api/v1/analyze/video` 가 업로드 파일에 대해 JSON 결과를 반환하는지 확인
6. **Outbox/retry 흐름 위치 확인**
   - 실패 적재 파일: `data/outbox/events.jsonl`
   - 재전송 엔드포인트: `POST /api/v1/retry-outbox`

---

## 6) Legacy 상태

- `legacy/outer-realtime-app/` 은 문서 스텁(역사적 참고)이며 공식 실행 대상이 아닙니다.
- `legacy/archived_realtime_reference/` 는 보관용 코드/에셋이며 실행 대상이 아닙니다.
- 신규 개발/검증/실행은 반드시 `AI_SAFETY_PRJ_1-main/` 기준으로 진행하세요.
