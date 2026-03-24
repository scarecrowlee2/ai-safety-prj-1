from __future__ import annotations

"""Global realtime analysis worker registry."""

from threading import Lock

from app.core.config import settings
from app.core.realtime_analysis_worker import RealtimeAnalysisWorker
from app.core.realtime_capture_registry import get_realtime_capture_service

_registry_lock = Lock()
_analysis_worker: RealtimeAnalysisWorker | None = None


def get_realtime_analysis_worker() -> RealtimeAnalysisWorker:
    """Return the shared realtime analysis worker instance."""

    global _analysis_worker
    with _registry_lock:
        if _analysis_worker is None:
            _analysis_worker = RealtimeAnalysisWorker(
                capture_service=get_realtime_capture_service(),
                target_fps=settings.realtime_analysis_fps,
            )
        return _analysis_worker


__all__ = ["get_realtime_analysis_worker"]
