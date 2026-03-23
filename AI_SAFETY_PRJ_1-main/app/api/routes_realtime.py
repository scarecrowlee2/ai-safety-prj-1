from __future__ import annotations

import json
import os
from contextlib import suppress
from collections import deque
from pathlib import Path
from string import Template
from time import sleep

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import numpy as np
from PIL import Image, ImageDraw

from app.core.webcam_reader import WebcamConfig, WebcamOpenError, WebcamReader

router = APIRouter(tags=["realtime"])
api_router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])

BASE_DIR = Path(__file__).resolve().parents[1]
REALTIME_TEMPLATE_PATH = BASE_DIR / "templates" / "realtime_dashboard.html"
REALTIME_EVENT_LOG_PATH = Path("data/realtime_events.jsonl")
RECENT_EVENT_LIMIT = 6
MJPEG_BOUNDARY = "frame"
DEFAULT_CAMERA_WIDTH = 960
DEFAULT_CAMERA_HEIGHT = 540
DEFAULT_CAMERA_FPS = 15.0


def _load_recent_events(limit: int = RECENT_EVENT_LIMIT) -> list[dict[str, object]]:
    """Read the most recent realtime JSONL events when a log file is available."""

    if not REALTIME_EVENT_LOG_PATH.exists():
        return []

    recent_lines: deque[str] = deque(maxlen=limit)
    with REALTIME_EVENT_LOG_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                recent_lines.append(stripped)

    events: list[dict[str, object]] = []
    for raw_line in reversed(recent_lines):
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        events.append(
            {
                "event_type": record.get("event_type", "unknown"),
                "message": record.get("message", "이벤트 정보가 없습니다."),
                "logged_at": record.get("logged_at"),
                "stream_timestamp_sec": record.get("stream_timestamp_sec"),
            }
        )

    return events


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

    limit = max(1, min(limit, 20))
    events = _load_recent_events(limit=limit)
    return {
        "events": events,
        "items": events,
        "log_path": str(REALTIME_EVENT_LOG_PATH),
    }


def _generate_webcam_stream():
    reader = WebcamReader(_webcam_config_from_env())

    try:
        reader.open()
    except (WebcamOpenError, ImportError, OSError, RuntimeError) as exc:
        message = f"웹캠을 열 수 없습니다: {exc}"
        yield _mjpeg_chunk(_build_status_frame(message))
        return

    frame_delay = 1.0 / max(reader.fps, 1.0)

    try:
        for webcam_frame in reader.frames():
            yield _mjpeg_chunk(_encode_jpeg(webcam_frame.image))
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
    raw_source = os.getenv("REALTIME_WEBCAM_SOURCE", "0").strip()
    source: int | str = int(raw_source) if raw_source.isdigit() else raw_source

    width = _optional_int_from_env("REALTIME_WEBCAM_WIDTH")
    height = _optional_int_from_env("REALTIME_WEBCAM_HEIGHT")
    fps = _optional_float_from_env("REALTIME_WEBCAM_FPS")

    return WebcamConfig(
        source=source,
        width=width or DEFAULT_CAMERA_WIDTH,
        height=height or DEFAULT_CAMERA_HEIGHT,
        fps=fps or DEFAULT_CAMERA_FPS,
    )


def _optional_int_from_env(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    with suppress(ValueError):
        return int(raw)
    return None


def _optional_float_from_env(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    with suppress(ValueError):
        return float(raw)
    return None


def _pil_image_to_jpeg_bytes(image: Image.Image) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
