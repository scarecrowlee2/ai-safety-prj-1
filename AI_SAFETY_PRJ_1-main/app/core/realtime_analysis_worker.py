from __future__ import annotations

"""Background latest-frame realtime analysis worker.

This worker consumes only the latest raw frame from the global capture service,
executes ``RealtimePipeline.analyze_frame`` at a bounded cadence, and stores a
thread-safe latest analysis snapshot for downstream readers.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from threading import Event, Lock, Thread
from time import sleep, time
from typing import Any

from app.core.realtime_capture import RealtimeCaptureService
from app.core.realtime_pipeline import BOX_COORD_SYSTEM_NORMALIZED_XYXY, RealtimePipeline

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class RealtimeAnalysisSnapshot:
    """Latest analysis snapshot produced by :class:`RealtimeAnalysisWorker`."""

    frame_id: int | None
    timestamp_sec: float | None
    captured_at: datetime | None
    analyzed_at: datetime
    source_size: tuple[int, int] | None
    states: dict[str, bool]
    objects: list[dict[str, Any]]
    banners: list[dict[str, Any]]
    ready: bool
    box_coord_system: str
    message: str
    error: str | None = None


class RealtimeAnalysisWorker:
    """Analyze the latest captured frame in background without queueing backlog."""

    def __init__(
        self,
        *,
        capture_service: RealtimeCaptureService,
        pipeline: RealtimePipeline | None = None,
        target_fps: float = 5.0,
        idle_sleep_sec: float = 0.05,
        thread_name: str = "realtime-analysis-worker",
    ) -> None:
        self._capture_service = capture_service
        self._pipeline = pipeline or RealtimePipeline()
        self._loop_sleep_sec = 1.0 / max(target_fps, 0.5)
        self._idle_sleep_sec = max(0.01, idle_sleep_sec)
        self._thread_name = thread_name

        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._running = False
        self._last_analyzed_frame_id: int | None = None
        self._latest_snapshot = RealtimeAnalysisSnapshot(
            frame_id=None,
            timestamp_sec=None,
            captured_at=None,
            analyzed_at=datetime.now(timezone.utc),
            source_size=None,
            states={},
            objects=[],
            banners=[],
            ready=False,
            box_coord_system=BOX_COORD_SYSTEM_NORMALIZED_XYXY,
            message="Analysis worker not started.",
            error=None,
        )

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return

            self._stop_event.clear()
            self._last_analyzed_frame_id = None
            self._latest_snapshot = RealtimeAnalysisSnapshot(
                frame_id=None,
                timestamp_sec=None,
                captured_at=None,
                analyzed_at=datetime.now(timezone.utc),
                source_size=None,
                states={},
                objects=[],
                banners=[],
                ready=False,
                box_coord_system=BOX_COORD_SYSTEM_NORMALIZED_XYXY,
                message="Waiting for webcam frames.",
                error=None,
            )
            self._thread = Thread(target=self._run_loop, name=self._thread_name, daemon=True)
            self._running = True
            self._thread.start()

    def stop(self) -> None:
        thread: Thread | None
        with self._lock:
            if not self._running and self._thread is None:
                return
            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=5.0)

        with self._lock:
            self._running = False
            self._thread = None

    def get_latest_snapshot(self) -> RealtimeAnalysisSnapshot:
        with self._lock:
            snapshot = self._latest_snapshot
            return RealtimeAnalysisSnapshot(
                frame_id=snapshot.frame_id,
                timestamp_sec=snapshot.timestamp_sec,
                captured_at=snapshot.captured_at,
                analyzed_at=snapshot.analyzed_at,
                source_size=snapshot.source_size,
                states=dict(snapshot.states),
                objects=[dict(item) for item in snapshot.objects],
                banners=[dict(item) for item in snapshot.banners],
                ready=snapshot.ready,
                box_coord_system=snapshot.box_coord_system,
                message=snapshot.message,
                error=snapshot.error,
            )

    def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                capture_status = self._capture_service.get_status()
                frame_snapshot = self._capture_service.get_latest_frame()

                if frame_snapshot is None:
                    message = "Waiting for webcam frames."
                    error = None
                    if capture_status.open_failed:
                        error = capture_status.last_error
                        message = "Webcam unavailable for analysis."
                    self._set_snapshot(
                        RealtimeAnalysisSnapshot(
                            frame_id=None,
                            timestamp_sec=None,
                            captured_at=None,
                            analyzed_at=datetime.fromtimestamp(time(), timezone.utc),
                            source_size=None,
                            states={},
                            objects=[],
                            banners=[],
                            ready=False,
                            box_coord_system=BOX_COORD_SYSTEM_NORMALIZED_XYXY,
                            message=message,
                            error=error,
                        )
                    )
                    sleep(self._idle_sleep_sec)
                    continue

                if frame_snapshot.frame_id == self._last_analyzed_frame_id:
                    sleep(self._idle_sleep_sec)
                    continue

                analyzed_at = datetime.fromtimestamp(time(), timezone.utc)
                try:
                    result = self._pipeline.analyze_frame(
                        frame=frame_snapshot.image,
                        timestamp_sec=frame_snapshot.timestamp_sec,
                        frame_id=frame_snapshot.frame_id,
                    )
                    overlay_payload = result.get("overlay_payload", {})
                    self._set_snapshot(
                        RealtimeAnalysisSnapshot(
                            frame_id=frame_snapshot.frame_id,
                            timestamp_sec=frame_snapshot.timestamp_sec,
                            captured_at=frame_snapshot.captured_at,
                            analyzed_at=analyzed_at,
                            source_size=frame_snapshot.source_size,
                            states=dict(overlay_payload.get("states", {})),
                            objects=[dict(item) for item in overlay_payload.get("objects", [])],
                            banners=[dict(item) for item in overlay_payload.get("banners", [])],
                            ready=True,
                            box_coord_system=str(overlay_payload.get("box_coord_system", BOX_COORD_SYSTEM_NORMALIZED_XYXY)),
                            message="ok",
                            error=None,
                        )
                    )
                    self._last_analyzed_frame_id = frame_snapshot.frame_id
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Realtime analysis worker failed to analyze frame.")
                    self._set_snapshot(
                        RealtimeAnalysisSnapshot(
                            frame_id=frame_snapshot.frame_id,
                            timestamp_sec=frame_snapshot.timestamp_sec,
                            captured_at=frame_snapshot.captured_at,
                            analyzed_at=analyzed_at,
                            source_size=frame_snapshot.source_size,
                            states={},
                            objects=[],
                            banners=[],
                            ready=False,
                            box_coord_system=BOX_COORD_SYSTEM_NORMALIZED_XYXY,
                            message="analysis failed",
                            error=str(exc),
                        )
                    )

                sleep(self._loop_sleep_sec)
        finally:
            with self._lock:
                self._running = False

    def _set_snapshot(self, snapshot: RealtimeAnalysisSnapshot) -> None:
        with self._lock:
            self._latest_snapshot = snapshot


__all__ = [
    "RealtimeAnalysisSnapshot",
    "RealtimeAnalysisWorker",
]
