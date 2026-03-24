# AI 스마트 생활안전 서비스 MVP - Python 감지 모듈

PRD와 첨부 계획서를 바탕으로 만든 FastAPI 기반 Python 프로젝트입니다.

> 저장소 루트의 외부 실시간 프로토타입은 최종 정리 후 문서/아카이브로만 남아 있습니다 (`legacy/outer-realtime-app/`, `legacy/archived_realtime_reference/`).
> 현재 공식 실행 및 신규 개발 경로는 이 디렉터리(`AI_SAFETY_PRJ_1-main/`)만 사용하세요.

핵심 목표는 다음 흐름을 데모 수준으로 재현하는 것입니다.

- 영상 분석
- 낙상(FALL) / 장시간 무응답(INACTIVE) 감지
- 이벤트 생성
- 스냅샷 저장
- JSON 결과 반환
- 선택적으로 Spring Boot 서버로 전송

## 이번 리팩토링에서 바뀐 점

- 낙상 감지를 Legacy `mp.solutions.pose` 에서 **MediaPipe Tasks Pose Landmarker** 기반으로 변경
- `Asia/Seoul` 타임존 데이터가 없는 환경에서도 **UTC fallback** 으로 서버가 바로 죽지 않도록 수정
- 낙상 모델 파일이 없거나 초기화 실패하면 전체 요청을 실패시키지 않고 **경고만 반환**하도록 수정
- `GET /api/v1/health` 에 감지기 상태와 경고를 포함하도록 확장

MediaPipe Python 가이드는 현재 Pose Landmarker 사용 시 `mediapipe` 패키지, `mediapipe.tasks.python.vision` 임포트, 로컬 `.task` 모델 파일, `BaseOptions(model_asset_path=...)`, `RunningMode.VIDEO`, `detect_for_video(...)` 흐름을 안내하고 있습니다. 또한 Legacy Solutions는 이미 as-is 상태입니다. citeturn116914view0turn638813search3

## 포함 범위

- `FA-001` 낙상/기절 감지
- `FA-002` 장시간 무응답 감지
- `notifier.py` 공통 이벤트 전송/재시도
- FastAPI 업로드 분석 API
- CLI 분석 실행기
- SQLite 기반 이벤트/캡처 기록 저장

## 보류 범위

- `FA-003` 폭행 의심 감지는 스캐폴드만 포함하고 기본 분석 플로우에서는 비활성화
- 실제 SMS/FCM/119 연동 없음
- 사용자별 취침 시간대 규칙 고도화 없음

## 프로젝트 구조

```text
ai_safety_mvp_project/
├─ app/
│  ├─ api/
│  │  └─ routes.py
│  ├─ core/
│  │  ├─ analyzer.py
│  │  ├─ config.py
│  │  ├─ timeutils.py
│  │  └─ video.py
│  ├─ detectors/
│  │  ├─ fall.py
│  │  ├─ inactive.py
│  │  └─ violence.py
│  ├─ storage/
│  │  ├─ event_store.py
│  │  ├─ metrics_logger.py
│  │  └─ snapshots.py
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ main.py
│  ├─ notifier.py
│  └─ schemas.py
├─ models/
├─ tests/
│  └─ test_event_store.py
├─ requirements.txt
├─ requirements-optional.txt
└─ .env.example
```

## 빠른 시작

### 1) 가상환경 생성

```bash
python -m venv .venv
```

### 2) 가상환경 활성화

#### Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

#### macOS / Linux

```bash
source .venv/bin/activate
```

### 3) 패키지 설치

```bash
pip install -r requirements.txt
```

YOLO 기반 사람 감지 게이트가 필요하면:

```bash
pip install -r requirements-optional.txt
```

### 4) 환경 파일 준비

```bash
cp .env.example .env
```

Windows에서는 직접 `.env` 파일을 만들어도 됩니다.

### 5) Pose Landmarker 모델 파일 준비

MediaPipe Python 가이드는 Pose Landmarker가 **로컬 `.task` 모델 파일**을 필요로 하고, `BaseOptions(model_asset_path=...)` 로 그 경로를 지정하도록 안내합니다. 기본 경로는 `./models/pose_landmarker.task` 입니다. citeturn116914view0

그래서 아래 둘 중 하나로 맞추면 됩니다.

- `models/pose_landmarker.task` 에 모델 파일을 넣기
- `.env` 에 `FALL_POSE_TASK_MODEL_PATH=/절대/경로/pose_landmarker.task` 지정하기

모델 파일이 없으면 서버는 계속 뜨지만, `FALL` 감지는 비활성화되고 응답의 `warnings` 와 `/health` 에 이유가 표시됩니다.

### 6) API 서버 실행

```bash
python -m uvicorn app.main:app --reload
```

실행 후 Swagger UI:

- `http://127.0.0.1:8000/docs`

## 먼저 확인할 것

### 헬스 체크

`GET /api/v1/health`

예상 응답 예시:

```json
{
  "status": "ok",
  "app": "AI Smart Safety MVP - Python Detector",
  "env": "dev",
  "timezone": "Asia/Seoul",
  "warnings": [
    "fall detector disabled: pose task model not found: models/pose_landmarker.task"
  ],
  "detectors": {
    "fall": {
      "enabled": false,
      "backend": "mediapipe_tasks",
      "model_path": "models/pose_landmarker.task",
      "reason": "pose task model not found: models/pose_landmarker.task"
    },
    "inactive": {
      "enabled": true,
      "backend": "opencv_mog2",
      "reason": ""
    }
  }
}
```

여기서 `fall.enabled=true` 가 떠야 낙상 감지가 실제로 동작합니다.

## API 예시

### 영상 업로드 분석

`POST /api/v1/analyze/video`

form-data:

- `resident_id`: 보호 대상자 ID
- `video`: mp4 파일
- `notify`: 선택, 기본 `false`

응답 예시:

```json
{
  "resident_id": 1,
  "video_name": "sample.mp4",
  "events": [],
  "warnings": [
    "fall detector disabled: pose task model not found: models/pose_landmarker.task"
  ]
}
```

모델 파일이 있고 감지가 되면 `events` 에 `FALL` 또는 `INACTIVE` 이벤트가 들어갑니다.

## CLI 실행

```bash
python -m app.cli --resident-id 1 --video ./samples/fall_demo.mp4
```

Spring Boot로 이벤트를 보내고 싶다면:

```bash
python -m app.cli --resident-id 1 --video ./samples/fall_demo.mp4 --notify
```

## 환경 변수

주요 변수는 `.env.example` 참고.

- `APP_TIMEZONE`
- `MODELS_DIR`
- `FALL_ENABLED`
- `FALL_POSE_TASK_MODEL_PATH`
- `FALL_HOLD_SECONDS`
- `FALL_ANGLE_THRESHOLD_DEG`
- `FALL_MIN_POSE_DETECTION_CONFIDENCE`
- `FALL_MIN_POSE_PRESENCE_CONFIDENCE`
- `FALL_MIN_TRACKING_CONFIDENCE`
- `INACTIVE_SECONDS`
- `MOTION_THRESHOLD`
- `ENABLE_YOLO_PERSON_GATE`
- `SPRING_BOOT_EVENT_URL`

## 구현 포인트

### 낙상 감지

- MediaPipe **Pose Landmarker Tasks API** 사용
- `.task` 모델 파일 로드
- `RunningMode.VIDEO` + `detect_for_video(...)` 사용
- 어깨 중심 ~ 엉덩이 중심 벡터 기반 몸통 각도 계산
- 수평에 가까운 자세가 일정 시간 유지되면 `FALL`

### 장시간 무응답

- OpenCV MOG2 배경 차분 사용
- 그림자 값(127) 제외
- 움직임 점수(`motion_ratio`)가 임계치 미만이면 무움직임 시간 누적
- 일정 시간 이상이면 `INACTIVE`

### 저장

- 이벤트는 SQLite 저장
- 스냅샷은 `data/snapshots/...` 경로 저장
- 전송 실패 시 `data/outbox/events.jsonl` 에 적재
- 프레임별 메트릭은 `data/metrics/*.jsonl` 에 저장

## 테스트

```bash
pytest
```

서버 기동 후 추천 확인 순서:

1. `GET /api/v1/health`
2. 정상 영상 업로드
3. 무응답 영상 업로드
4. `warnings` 와 `data/metrics/*.jsonl` 확인
5. 모델 파일을 넣은 뒤 낙상 영상 업로드

## 다음 추천 단계

- Pose Landmarker 모델 파일을 프로젝트에 포함하거나 배포 스크립트로 자동 준비
- Spring Boot `/internal/detection/events`와 실제 연결
- 보호자별 취침 시간대 설정 연동
- WebSocket/SSE 기반 실시간 대시보드 반영
- 이벤트 중복 억제 정책 고도화
- 임계치 외부 설정/관리 UI 추가
