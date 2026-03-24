from __future__ import annotations

"""Global realtime capture service registry.

This module owns a process-wide singleton-like capture service instance so the
webcam can be started/stopped from app lifespan and reused by routes.
"""

from threading import Lock

from app.core.config import settings
from app.core.realtime_capture import RealtimeCaptureService
from app.core.webcam_reader import WebcamConfig

_registry_lock = Lock()
_capture_service: RealtimeCaptureService | None = None


def get_realtime_capture_service() -> RealtimeCaptureService:
    """Return the shared realtime capture service instance.

    The service object is created lazily and reused for the process lifetime.
    """

    global _capture_service
    with _registry_lock:
        if _capture_service is None:
            _capture_service = RealtimeCaptureService(config=_webcam_config_from_settings())
        return _capture_service


def _webcam_config_from_settings() -> WebcamConfig:
    """Build webcam configuration for the global capture service."""

    raw_source = settings.realtime_webcam_source
    source: int | str = int(raw_source) if raw_source.isdigit() else raw_source

    return WebcamConfig(
        source=source,
        width=settings.realtime_webcam_width,
        height=settings.realtime_webcam_height,
        fps=settings.realtime_webcam_fps,
        backend=settings.realtime_webcam_backend,
    )


__all__ = ["get_realtime_capture_service"]
