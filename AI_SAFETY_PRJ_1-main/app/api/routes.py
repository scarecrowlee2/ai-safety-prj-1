from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.analyzer import VideoAnalyzer
from app.core.config import settings
from app.notifier import EventNotifier
from app.storage.event_store import EventStore

router = APIRouter(prefix="/api/v1", tags=["analyzer"])


# 이 함수는 서비스 상태와 감지기 진단 정보를 반환합니다.
@router.get("/health")
def health() -> dict:
    analyzer = VideoAnalyzer()
    diagnostics = analyzer.diagnostics()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        **diagnostics,
    }


# 이 함수는 영상을 분석해 감지 이벤트 목록과 부가 정보를 생성합니다.
@router.post("/analyze/video")
async def analyze_video(
    resident_id: int = Form(...),
    video: UploadFile = File(...),
    notify: bool = Form(False),
) -> dict:
    suffix = Path(video.filename or "upload.mp4").suffix or ".mp4"
    upload_path = settings.temp_upload_dir / f"resident_{resident_id}_{Path(video.filename or 'upload').stem}{suffix}"

    content = await video.read()
    upload_path.write_bytes(content)

    try:
        analyzer = VideoAnalyzer()
        result = analyzer.analyze_video(resident_id=resident_id, video_path=upload_path)
        if notify:
            notifier = EventNotifier(EventStore())
            notification_results = [notifier.send_event(event).model_dump() for event in result.events]
            payload = result.model_dump(mode="json")
            payload["notification_results"] = notification_results
            return payload
        return result.model_dump(mode="json")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# 이 함수는 전송에 실패해 outbox에 남아 있는 이벤트 재전송을 시도합니다.
@router.post("/retry-outbox")
def retry_outbox() -> dict:
    notifier = EventNotifier(EventStore())
    return notifier.retry_send()
