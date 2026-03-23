from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from string import Template

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response

router = APIRouter(tags=["realtime"])
api_router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])

BASE_DIR = Path(__file__).resolve().parents[1]
REALTIME_TEMPLATE_PATH = BASE_DIR / "templates" / "realtime_dashboard.html"
REALTIME_EVENT_LOG_PATH = Path("data/realtime_events.jsonl")
RECENT_EVENT_LIMIT = 6


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
def realtime_video() -> Response:
    """Return a lightweight SVG placeholder until realtime streaming is wired."""

    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" role="img" aria-label="Realtime video placeholder">
      <defs>
        <linearGradient id="bg" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stop-color="#0f172a" />
          <stop offset="100%" stop-color="#111827" />
        </linearGradient>
      </defs>
      <rect width="960" height="540" fill="url(#bg)" />
      <rect x="48" y="48" width="864" height="444" rx="28" fill="#020617" stroke="#334155" stroke-width="4" />
      <circle cx="140" cy="114" r="10" fill="#22c55e" />
      <text x="170" y="122" fill="#e2e8f0" font-size="28" font-family="Inter, Arial, sans-serif">Realtime stream placeholder</text>
      <text x="96" y="220" fill="#94a3b8" font-size="30" font-family="Inter, Arial, sans-serif">
        /realtime/video is reserved for Task 2-3 backend stream wiring.
      </text>
      <text x="96" y="278" fill="#94a3b8" font-size="26" font-family="Inter, Arial, sans-serif">
        The dashboard asset migration is complete and safe to load now.
      </text>
      <text x="96" y="382" fill="#38bdf8" font-size="24" font-family="Inter, Arial, sans-serif">
        Once MJPEG streaming is ready, replace this placeholder response.
      </text>
    </svg>
    """.strip()
    return Response(content=svg, media_type="image/svg+xml")


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
