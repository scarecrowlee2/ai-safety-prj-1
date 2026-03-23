from __future__ import annotations

"""Scaffold webcam reader abstractions for future live capture support.

This module is reserved for webcam-specific capture management so realtime input
handling can remain separate from file-based video analysis in app.core.video.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class WebcamConfig:
    """Minimal configuration container for a future webcam capture source."""

    source: int | str = 0
    width: int | None = None
    height: int | None = None
    fps: float | None = None


class WebcamReader:
    """Placeholder webcam reader interface.

    Future work can wrap cv2.VideoCapture or another backend while keeping live
    capture concerns isolated from upload-based processing.
    """

    def __init__(self, config: WebcamConfig | None = None) -> None:
        self.config = config or WebcamConfig()
        self._is_open = False

    def open(self) -> None:
        """Prepare the webcam source for future frame reads."""

        self._is_open = True

    def read_frame(self) -> Any | None:
        """Return the next webcam frame when live capture is implemented later."""

        if not self._is_open:
            return None
        return None

    def close(self) -> None:
        """Release any future webcam resources and mark the reader closed."""

        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Expose whether the placeholder reader is currently marked as open."""

        return self._is_open
