from __future__ import annotations

"""App-wide webcam capture service for realtime features.

This module provides a singleton-friendly service that opens the webcam once,
updates only the latest raw frame in background, and exposes thread-safe
snapshot/state access for downstream realtime routes.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from threading import Event, Lock, Thread
from time import monotonic, sleep, time
from typing import TYPE_CHECKING

from app.core.webcam_reader import WebcamConfig, WebcamOpenError, WebcamReader

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class RealtimeFrameSnapshot:
    """Immutable latest-frame snapshot returned by :class:`RealtimeCaptureService`.

    Attributes:
        frame_id: Monotonic frame number from the capture loop.
        timestamp_sec: Stream-relative timestamp for the captured frame.
        captured_at: UTC timestamp when this snapshot was stored by the service.
        source_size: ``(width, height)`` tuple from the frame shape.
        image: Raw BGR frame image from webcam.
    """

    frame_id: int
    timestamp_sec: float
    captured_at: datetime
    source_size: tuple[int, int]
    image: np.ndarray


@dataclass(slots=True, frozen=True)
class RealtimeCaptureStatus:
    """Compact state payload for service health and diagnostics."""

    running: bool
    started_at: datetime | None
    stopped_at: datetime | None
    open_failed: bool
    frame_id: int | None
    last_timestamp_sec: float | None
    last_frame_at: datetime | None
    source_size: tuple[int, int] | None
    last_error: str | None


class RealtimeCaptureService:
    """Background webcam service that keeps only the latest raw frame.

    The service is intentionally analysis-agnostic: it only captures and stores
    the latest source frame metadata, leaving processing/overlay work to later
    pipeline stages.
    """

    def __init__(
        self,
        config: WebcamConfig,
        *,
        read_fail_sleep_sec: float = 0.05,
        thread_name: str = "realtime-capture-service",
    ) -> None:
        """Initialize the capture service.

        Args:
            config: Webcam source configuration.
            read_fail_sleep_sec: Backoff delay when frame reads fail.
            thread_name: Background thread name for observability.
        """

        self._config = config
        self._read_fail_sleep_sec = max(0.01, read_fail_sleep_sec)
        self._thread_name = thread_name

        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._reader: WebcamReader | None = None

        self._latest_frame: RealtimeFrameSnapshot | None = None
        self._running = False
        self._open_failed = False
        self._last_error: str | None = None
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        """Return whether the background capture loop is currently active."""

        with self._lock:
            return self._running

    def start(self) -> None:
        """Start the background capture loop if it is not already running."""

        with self._lock:
            if self._running:
                return

            self._stop_event.clear()
            self._open_failed = False
            self._last_error = None
            self._started_at = datetime.now(timezone.utc)
            self._stopped_at = None

            self._thread = Thread(target=self._run_capture_loop, name=self._thread_name, daemon=True)
            self._running = True
            self._thread.start()

    def stop(self) -> None:
        """Stop capture thread and release webcam resources safely."""

        thread: Thread | None
        with self._lock:
            if not self._running and self._thread is None:
                return
            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=5.0)

        with self._lock:
            self._release_reader_locked()
            self._running = False
            self._thread = None
            self._stopped_at = datetime.now(timezone.utc)

    def get_latest_frame(self) -> RealtimeFrameSnapshot | None:
        """Return the latest frame snapshot with a copied image, if available."""

        with self._lock:
            snapshot = self._latest_frame
            if snapshot is None:
                return None
            return RealtimeFrameSnapshot(
                frame_id=snapshot.frame_id,
                timestamp_sec=snapshot.timestamp_sec,
                captured_at=snapshot.captured_at,
                source_size=snapshot.source_size,
                image=snapshot.image.copy(),
            )

    def get_status(self) -> RealtimeCaptureStatus:
        """Return current service state including open/read failure indicators."""

        with self._lock:
            latest = self._latest_frame
            return RealtimeCaptureStatus(
                running=self._running,
                started_at=self._started_at,
                stopped_at=self._stopped_at,
                open_failed=self._open_failed,
                frame_id=latest.frame_id if latest else None,
                last_timestamp_sec=latest.timestamp_sec if latest else None,
                last_frame_at=latest.captured_at if latest else None,
                source_size=latest.source_size if latest else None,
                last_error=self._last_error,
            )

    def _run_capture_loop(self) -> None:
        """Capture webcam frames continuously and keep only the latest snapshot."""

        reader = WebcamReader(self._config)
        with self._lock:
            self._reader = reader

        try:
            reader.open()
        except (WebcamOpenError, ImportError, OSError, RuntimeError) as exc:
            logger.exception("Failed to open webcam source in capture service.")
            with self._lock:
                self._open_failed = True
                self._last_error = str(exc)
                self._running = False
                self._stopped_at = datetime.now(timezone.utc)
                self._release_reader_locked()
            return

        stream_started_monotonic = monotonic()

        try:
            while not self._stop_event.is_set():
                webcam_frame = reader.read_frame()
                if webcam_frame is None:
                    sleep(self._read_fail_sleep_sec)
                    continue

                image = webcam_frame.image
                height, width = image.shape[:2]
                timestamp_sec = float(webcam_frame.timestamp_sec)
                if timestamp_sec <= 0.0:
                    timestamp_sec = max(0.0, monotonic() - stream_started_monotonic)

                snapshot = RealtimeFrameSnapshot(
                    frame_id=int(webcam_frame.frame_index),
                    timestamp_sec=timestamp_sec,
                    captured_at=datetime.fromtimestamp(time(), timezone.utc),
                    source_size=(int(width), int(height)),
                    image=image,
                )

                with self._lock:
                    self._latest_frame = snapshot
                    self._last_error = None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected webcam capture loop failure.")
            with self._lock:
                self._last_error = str(exc)
        finally:
            with self._lock:
                self._release_reader_locked()
                self._running = False
                self._stopped_at = datetime.now(timezone.utc)

    def _release_reader_locked(self) -> None:
        """Close and clear the current reader. Caller must hold ``self._lock``."""

        if self._reader is None:
            return

        try:
            self._reader.close()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to close webcam reader cleanly.")
        finally:
            self._reader = None


__all__ = [
    "RealtimeCaptureService",
    "RealtimeCaptureStatus",
    "RealtimeFrameSnapshot",
]
