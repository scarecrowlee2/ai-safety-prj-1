from __future__ import annotations

"""Webcam-specific frame capture helpers for future realtime routes.

This module intentionally keeps live camera access separate from the uploaded
file reader in :mod:`app.core.video`.
"""

from dataclasses import dataclass
import logging
import os
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


class WebcamOpenError(RuntimeError):
    """Raised when a webcam source cannot be opened."""


@dataclass(slots=True)
class WebcamConfig:
    """Configuration for a live webcam capture source."""

    source: int | str = 0
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    backend: int | None = None


@dataclass(slots=True)
class WebcamFrame:
    """A single frame captured from a webcam source."""

    frame_index: int
    timestamp_sec: float
    image: np.ndarray


class WebcamReader:
    """Small reusable wrapper around ``cv2.VideoCapture`` for webcam input."""

    def __init__(self, config: WebcamConfig | None = None) -> None:
        self.config = config or WebcamConfig()
        self._capture = None
        self._fps = float(self.config.fps) if self.config.fps and self.config.fps > 0 else 0.0
        self._frame_index = 0

    def open(self) -> None:
        """Open the configured webcam source if it is not already open."""

        if self.is_open:
            return

        capture = self._create_capture()
        if not capture.isOpened():
            capture.release()
            raise WebcamOpenError(f"Unable to open webcam source: {self.config.source!r}")

        self._apply_capture_settings(capture)
        detected_fps = float(capture.get(self._cv2().CAP_PROP_FPS) or 0.0)
        if detected_fps > 0:
            self._fps = detected_fps

        self._capture = capture
        self._frame_index = 0

    def read_frame(self) -> WebcamFrame | None:
        """Read the next webcam frame or return ``None`` when capture ends."""

        if not self.is_open:
            self.open()

        assert self._capture is not None
        ok, frame = self._capture.read()
        if not ok:
            return None

        frame_index = self._frame_index
        self._frame_index += 1
        fps = self.fps
        timestamp_sec = frame_index / fps if fps > 0 else 0.0
        return WebcamFrame(
            frame_index=frame_index,
            timestamp_sec=timestamp_sec,
            image=frame,
        )

    def frames(self) -> Iterator[WebcamFrame]:
        """Yield webcam frames until capture stops producing frames."""

        while True:
            frame = self.read_frame()
            if frame is None:
                break
            yield frame

    def close(self) -> None:
        """Release the webcam resource safely."""

        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def release(self) -> None:
        """Backward-compatible alias for :meth:`close`."""

        self.close()

    @property
    def is_open(self) -> bool:
        """Whether the webcam capture is currently open."""

        return self._capture is not None and bool(self._capture.isOpened())

    @property
    def fps(self) -> float:
        """Reported webcam FPS, with a conservative fallback when unavailable."""

        return self._fps if self._fps > 0 else 30.0

    def __enter__(self) -> WebcamReader:
        self.open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    @staticmethod
    def _cv2():
        import cv2

        return cv2

    def _create_capture(self):
        cv2 = self._cv2()

        if self.config.backend is not None:
            return cv2.VideoCapture(self.config.source, self.config.backend)

        if isinstance(self.config.source, int) and os.name == "nt" and hasattr(cv2, "CAP_DSHOW"):
            capture = cv2.VideoCapture(self.config.source, cv2.CAP_DSHOW)
            if capture.isOpened():
                return capture
            capture.release()

        return cv2.VideoCapture(self.config.source)

    def _apply_capture_settings(self, capture) -> None:
        cv2 = self._cv2()

        if self.config.width is not None:
            self._try_set_capture_property(
                capture,
                cv2.CAP_PROP_FRAME_WIDTH,
                float(self.config.width),
                property_name="width",
            )
        if self.config.height is not None:
            self._try_set_capture_property(
                capture,
                cv2.CAP_PROP_FRAME_HEIGHT,
                float(self.config.height),
                property_name="height",
            )
        if self.config.fps is not None and self.config.fps > 0:
            self._try_set_capture_property(
                capture,
                cv2.CAP_PROP_FPS,
                float(self.config.fps),
                property_name="fps",
            )

        if self.config.fps is not None and self.config.fps > 0:
            self._fps = float(self.config.fps)

    @staticmethod
    def _try_set_capture_property(capture, property_id: int, value: float, *, property_name: str) -> None:
        cv2 = WebcamReader._cv2()
        try:
            applied = bool(capture.set(property_id, value))
        except cv2.error as exc:
            logger.warning(
                "Webcam capture property '%s' could not be applied (value=%s): %s",
                property_name,
                value,
                exc,
            )
            return

        if not applied:
            logger.warning(
                "Webcam capture property '%s' was rejected by backend (value=%s); using device default.",
                property_name,
                value,
            )


__all__ = [
    "WebcamConfig",
    "WebcamFrame",
    "WebcamOpenError",
    "WebcamReader",
]
