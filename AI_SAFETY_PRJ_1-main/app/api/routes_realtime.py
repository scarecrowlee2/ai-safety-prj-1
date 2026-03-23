from __future__ import annotations

"""Placeholder routes for future realtime monitoring features.

This module keeps realtime-specific route registration isolated so the inner
FastAPI app can expose dashboard-friendly paths without implementing streaming
or migrating legacy outer-app business logic yet.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

router = APIRouter(tags=["realtime"])
api_router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])


@router.get("/realtime", response_class=HTMLResponse)
def realtime_dashboard() -> str:
    """Return a minimal placeholder dashboard page for future realtime UI work."""

    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <title>Realtime Dashboard Placeholder</title>
      </head>
      <body>
        <main>
          <h1>Realtime dashboard placeholder</h1>
          <p>Realtime templates and live streaming will be connected in a later step.</p>
        </main>
      </body>
    </html>
    """


@router.get("/realtime/video", response_class=PlainTextResponse)
def realtime_video() -> str:
    """Return a lightweight placeholder response for the future video feed."""

    return "Realtime video placeholder"


@api_router.get("/events", response_class=JSONResponse)
def realtime_events() -> dict[str, list[dict[str, object]]]:
    """Return an empty event feed structure until realtime ingestion is added."""

    return {"items": []}
