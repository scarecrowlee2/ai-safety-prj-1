from __future__ import annotations

"""Scaffold routes for future realtime monitoring features.

This module intentionally provides only placeholder endpoints and router structure
for the inner FastAPI application. Full webcam streaming, MJPEG responses, and
recent-event retrieval will be wired in later tasks.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])


@router.get("/status")
def realtime_status() -> dict[str, str]:
    """Return a lightweight status payload for the future realtime subsystem.

    This placeholder endpoint is safe to import and can later be expanded into
    health or readiness checks for webcam and pipeline services.
    """

    return {
        "status": "not_configured",
        "message": "Realtime routes are scaffolded but not yet wired to live processing.",
    }


# Future responsibilities for this module:
# - Serve the realtime monitoring page/template.
# - Expose a live video stream endpoint.
# - Return recent detection events for the dashboard.
