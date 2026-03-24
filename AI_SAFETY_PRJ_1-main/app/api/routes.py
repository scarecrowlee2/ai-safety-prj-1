from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.analyzer import VideoAnalyzer, get_video_analyzer as _get_shared_video_analyzer
from app.core.config import settings
from app.notifier import EventNotifier
from app.storage.event_store import EventStore

router = APIRouter(prefix="/api/v1", tags=["analyzer"])
MIN_UPLOAD_CHUNK_SIZE = 64 * 1024
MAX_UPLOAD_STEM_LENGTH = 80


def _build_upload_path(resident_id: int, original_filename: str | None) -> Path:
    source_name = Path(original_filename or "upload.mp4").name
    source_path = Path(source_name)
    suffix = source_path.suffix or ".mp4"
    raw_stem = source_path.stem or "upload"
    safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw_stem).strip("_") or "upload"
    trimmed_stem = safe_stem[:MAX_UPLOAD_STEM_LENGTH]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    unique_token = uuid4().hex[:12]
    return settings.temp_upload_dir / f"resident_{resident_id}_{timestamp}_{unique_token}_{trimmed_stem}{suffix}"


def get_video_analyzer() -> VideoAnalyzer:
    return _get_shared_video_analyzer(factory=VideoAnalyzer)


# 이 함수는 서비스 상태와 감지기 진단 정보를 반환합니다.
@router.get("/health")
def health() -> dict:
    analyzer = get_video_analyzer()
    diagnostics = analyzer.diagnostics()
    inactive_mode = diagnostics.get("detectors", {}).get("inactive", {}).get("mode", "unknown")
    service_status = "ok"
    if inactive_mode in {"degraded", "error", "disabled"}:
        service_status = "degraded"
    return {
        "status": service_status,
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
    upload_path = _build_upload_path(resident_id=resident_id, original_filename=video.filename)
    chunk_size = max(settings.upload_write_chunk_size, MIN_UPLOAD_CHUNK_SIZE)

    try:
        with upload_path.open("wb") as upload_buffer:
            while chunk := await video.read(chunk_size):
                upload_buffer.write(chunk)

        analyzer = get_video_analyzer()
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
    finally:
        await video.close()
        if not settings.keep_temp_upload_files:
            upload_path.unlink(missing_ok=True)


# 이 함수는 전송에 실패해 outbox에 남아 있는 이벤트 재전송을 시도합니다.
@router.post("/retry-outbox")
def retry_outbox() -> dict:
    notifier = EventNotifier(EventStore())
    return notifier.retry_send()
