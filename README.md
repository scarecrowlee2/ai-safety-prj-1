# AI Smart Safety MVP Repository Guide

이 저장소의 실제 실행 대상은 내부 프로젝트 디렉터리 하나입니다.

## Official application

- **Official root:** `AI_SAFETY_PRJ_1-main/`
- **Official FastAPI entrypoint:** `app.main:app`

즉, 이 저장소에서는 `AI_SAFETY_PRJ_1-main/`만 현재 운영 기준 코드로 사용합니다.

---

## Quick start

아래 명령은 저장소 루트가 아니라 **`AI_SAFETY_PRJ_1-main/` 디렉터리 안에서** 실행합니다.

```bash
cd AI_SAFETY_PRJ_1-main

python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env        # Windows에서는 수동 복사 또는 copy 사용

uvicorn app.main:app --reload
````

YOLO person gate를 활성화해서 운영할 경우 optional 의존성도 함께 설치합니다.

```bash
pip install -r requirements-optional.txt
```

---

## Primary validation routes

서버 실행 후 아래 경로로 기본 점검을 진행합니다.

* `GET /docs`
* `GET /api/v1/health`
* `GET /realtime`
* `GET /realtime/video`
* `GET /api/v1/realtime/events`
* `GET /api/v1/realtime/status`
* `POST /api/v1/analyze/video`
* `POST /api/v1/retry-outbox`

---

## What each route is for

* `/docs`
  FastAPI Swagger 문서 화면입니다.

* `/api/v1/health`
  서비스 상태, detector 상태, 경고 항목을 확인하는 진단용 API입니다.

* `/realtime`
  실시간 안전 모니터링 대시보드 UI입니다.

* `/realtime/video`
  대시보드에서 사용하는 MJPEG 영상 스트림입니다.

* `/api/v1/realtime/events`
  최근 실시간 이벤트 목록을 조회하는 API입니다.

* `/api/v1/realtime/status`
  낙상, 비활성, 폭행 감지 상태 요약을 조회하는 API입니다.

* `/api/v1/analyze/video`
  업로드한 영상 파일을 분석하는 API입니다.

* `/api/v1/retry-outbox`
  실패한 알림 전송 건의 재시도를 수행하는 API입니다.

---

## Project scope

이 프로젝트는 크게 두 흐름으로 구성됩니다.

### 1. 업로드 분석

* 대상 API: `POST /api/v1/analyze/video`
* 현재 지원 detector: `fall`, `inactive`
* 현재 미지원 detector: `violence`
  (`violence`는 실시간 파이프라인 전용)

### 2. 실시간 감지

* 대상 경로: `/realtime`, `/realtime/video`, `/api/v1/realtime/events`, `/api/v1/realtime/status`
* 실시간 파이프라인 detector 범위: `fall`, `inactive`, `violence`

---

## Repository structure

```text
.
├── README.md
└── AI_SAFETY_PRJ_1-main/
    ├── app/
    ├── data/
    ├── models/
    ├── tests/
    ├── .env.example
    ├── requirements.txt
    ├── requirements-optional.txt
    └── README.md
```

* 루트 `README.md`는 저장소 진입 안내 문서입니다.
* 실제 실행/설정/운영 기준 설명은 `AI_SAFETY_PRJ_1-main/README.md`를 따릅니다.

---

## Source of truth

현재 저장소 기준 단일 기준 코드는 아래입니다.

* **Application root:** `AI_SAFETY_PRJ_1-main/`
* **Entrypoint:** `app.main:app`

실행, 점검, 수정, 배포 판단은 모두 이 경로를 기준으로 진행합니다.

---

## Additional notes

* 웹캠이 연결되지 않았거나 열기에 실패한 경우 `/realtime/video`는 fallback 상태 프레임을 반환할 수 있습니다.
* `inactive` detector를 운영에서 안정적으로 사용하려면 `ENABLE_YOLO_PERSON_GATE=true` 구성을 권장합니다.
* detector의 실제 준비 상태는 `GET /api/v1/health`에서 확인할 수 있습니다.

---

## Detailed documentation

자세한 설정, 실행, 점검 절차는 아래 문서를 확인합니다.

* `AI_SAFETY_PRJ_1-main/README.md`
* `AI_SAFETY_PRJ_1-main/REALTIME_DETECTION_GUIDE.md`
* `AI_SAFETY_PRJ_1-main/AI_SAFETY_PRJ_method_flow.md`

````

추가로 보면, 이 버전은 **루트 README 전용**으로 깔끔하다.  
즉:

- `legacy` 언급 완전 제거
- 현재 살아있는 실행 경로만 남김
- 저장소 입구 문서 역할만 하도록 단순화

다음 커밋 때는 보통 이렇게 묶으면 좋다.

```bash
git add README.md
git commit -m "docs: rewrite root README after legacy removal"
````
