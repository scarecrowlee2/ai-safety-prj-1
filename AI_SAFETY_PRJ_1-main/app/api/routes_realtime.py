from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from time import sleep

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import numpy as np
from PIL import Image, ImageDraw

from app.core.realtime_pipeline import RealtimePipeline
from app.core.realtime_notifier_policy import RealtimeNotifierIntegration
from app.core.config import settings
from app.storage.event_logger import EventLogger
from app.storage.realtime_event_store import RealtimeEventStore
from app.notifier import EventNotifier
from app.storage.event_store import EventStore
from app.core.webcam_reader import WebcamConfig, WebcamOpenError, WebcamReader

router = APIRouter(tags=["realtime"])
api_router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])

BASE_DIR = Path(__file__).resolve().parents[1]
REALTIME_TEMPLATE_PATH = BASE_DIR / "templates" / "realtime_dashboard.html"
REALTIME_EVENT_LOG_PATH = settings.realtime_event_log_path
RECENT_EVENT_LIMIT = settings.realtime_recent_event_limit
RECENT_EVENT_MAX_LIMIT = settings.realtime_recent_event_max_limit
MJPEG_BOUNDARY = settings.realtime_mjpeg_boundary
DEFAULT_CAMERA_WIDTH = settings.realtime_webcam_width
DEFAULT_CAMERA_HEIGHT = settings.realtime_webcam_height
STATUS_EVENT_TYPES = ("fall", "inactive", "violence")
STATUS_EVENT_RECENCY_SECONDS = 60


realtime_event_logger = EventLogger(str(REALTIME_EVENT_LOG_PATH))
realtime_event_store = RealtimeEventStore(feed=realtime_event_logger.store.feed)
realtime_pipeline = RealtimePipeline(event_logger=realtime_event_logger)
realtime_notifier = RealtimeNotifierIntegration(notifier=EventNotifier(EventStore()))


def get_realtime_pipeline() -> RealtimePipeline:
    return realtime_pipeline


def _load_recent_events(limit: int = RECENT_EVENT_LIMIT) -> list[dict[str, object]]:
    """Read recent realtime dashboard events from the event-store feed path."""

    return realtime_event_store.list_recent_feed(limit=limit)


@router.get("/realtime", response_class=HTMLResponse)
def realtime_dashboard() -> HTMLResponse:
    """Render the migrated realtime dashboard template from the inner app."""

    template = Template(REALTIME_TEMPLATE_PATH.read_text(encoding="utf-8"))
    html = template.safe_substitute(
        service_title="AI Safety Realtime Monitor",
        service_description="낙상·무응답·폭행 이상 징후를 실시간으로 감시하는 운영 대시보드입니다.",
        log_path=str(REALTIME_EVENT_LOG_PATH),
        monitoring_state="READY",
        recent_event_count=RECENT_EVENT_LIMIT,
        css_path="/static/css/realtime_dashboard.css",
        js_path="/static/js/realtime_dashboard.js",
        video_path="/realtime/video",
        events_path="/api/v1/realtime/events",
    )
    return HTMLResponse(html)


@router.get("/realtime/video")
def realtime_video() -> StreamingResponse:
    """Stream live webcam frames to the inner realtime dashboard as MJPEG."""

    return StreamingResponse(
        _generate_webcam_stream(),
        media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@api_router.get("/events", response_class=JSONResponse)
def realtime_events(limit: int = RECENT_EVENT_LIMIT) -> dict[str, object]:
    """Return recent realtime events if available, or an empty feed payload."""

    limit = max(1, min(limit, RECENT_EVENT_MAX_LIMIT))
    events = _load_recent_events(limit=limit)
    return {
        "events": events,
        "items": events,
        "log_path": str(REALTIME_EVENT_LOG_PATH),
    }


@api_router.get("/status", response_class=JSONResponse)
def realtime_status() -> dict[str, object]:
    """Return a compact status summary for dashboard status badges."""

    events = _load_recent_events(limit=RECENT_EVENT_MAX_LIMIT)
    summary = _summarize_realtime_status(events)
    return {
        **summary,
        "last_updated": datetime.now(UTC).isoformat(),
    }


def _summarize_realtime_status(events: list[dict[str, object]]) -> dict[str, str]:
    now = datetime.now(UTC)
    status_by_type = {event_type: "normal" for event_type in STATUS_EVENT_TYPES}

    for event in events:
        event_type = event.get("event_type")
        if not isinstance(event_type, str) or event_type not in status_by_type:
            continue

        logged_at = event.get("logged_at")
        parsed_at = _parse_logged_at(logged_at)
        if parsed_at is None:
            continue

        event_age = (now - parsed_at).total_seconds()
        if 0 <= event_age <= STATUS_EVENT_RECENCY_SECONDS:
            status_by_type[event_type] = "warning"

    status_by_type["state"] = "warning" if any(
        status == "warning" for status in status_by_type.values()
    ) else "normal"
    return status_by_type


def _parse_logged_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    normalized = value.replace("Z", "+00:00")
    with suppress(ValueError):
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    return None


def _generate_webcam_stream(pipeline: RealtimePipeline | None = None):
    active_pipeline = pipeline if pipeline is not None else get_realtime_pipeline()
    reader = WebcamReader(_webcam_config_from_env())

    try:
        reader.open()
    except (WebcamOpenError, ImportError, OSError, RuntimeError) as exc:
        message = f"웹캠을 열 수 없습니다: {exc}"
        yield _mjpeg_chunk(_build_status_frame(message))
        return

    frame_delay = 1.0 / max(reader.fps, 1.0)

    try:
        stream_started_at = 0.0
        for frame_index, webcam_frame in enumerate(reader.frames()):
            timestamp_sec = getattr(webcam_frame, "timestamp_sec", stream_started_at + (frame_index * frame_delay))
            result = active_pipeline.process_frame(webcam_frame.image, float(timestamp_sec))
            new_logged_events = result.metadata.get("new_logged_events")
            if isinstance(new_logged_events, list):
                realtime_notifier.notify_logged_events(new_logged_events)
            yield _mjpeg_chunk(_encode_jpeg(result.frame))
            sleep(frame_delay)
    finally:
        with suppress(Exception):
            reader.close()


def _mjpeg_chunk(frame_bytes: bytes) -> bytes:
    return (
        f"--{MJPEG_BOUNDARY}\r\n"
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + frame_bytes + b"\r\n"


def _build_status_frame(message: str) -> bytes:
    image = Image.new("RGB", (DEFAULT_CAMERA_WIDTH, DEFAULT_CAMERA_HEIGHT), (15, 23, 42))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, DEFAULT_CAMERA_WIDTH - 48, DEFAULT_CAMERA_HEIGHT - 48), radius=24, fill=(2, 6, 23), outline=(71, 85, 105), width=2)
    draw.ellipse((98, 98, 122, 122), fill=(255, 165, 0))
    draw.text((145, 104), "Realtime webcam unavailable", fill=(226, 232, 240))

    for index, line in enumerate(_wrap_text(message, 52)):
        y = 210 + index * 34
        draw.text((96, y), line, fill=(148, 163, 184))

    draw.text(
        (96, DEFAULT_CAMERA_HEIGHT - 92),
        "Connect a camera to replace this fallback frame.",
        fill=(56, 189, 248),
    )
    return _pil_image_to_jpeg_bytes(image)


def _encode_jpeg(image: np.ndarray) -> bytes:
    return _pil_image_to_jpeg_bytes(Image.fromarray(image[:, :, ::-1]))


def _wrap_text(value: str, max_chars: int) -> list[str]:
    words = value.split()
    if not words:
        return [""]

    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join([*current, word])
        if current and len(trial) > max_chars:
            lines.append(" ".join(current))
            current = [word]
            continue
        current.append(word)

    if current:
        lines.append(" ".join(current))
    return lines


def _webcam_config_from_env() -> WebcamConfig:
    raw_source = settings.realtime_webcam_source
    source: int | str = int(raw_source) if raw_source.isdigit() else raw_source

    return WebcamConfig(
        source=source,
        width=settings.realtime_webcam_width,
        height=settings.realtime_webcam_height,
        fps=settings.realtime_webcam_fps,
        backend=settings.realtime_webcam_backend,
    )


def _pil_image_to_jpeg_bytes(image: Image.Image) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
