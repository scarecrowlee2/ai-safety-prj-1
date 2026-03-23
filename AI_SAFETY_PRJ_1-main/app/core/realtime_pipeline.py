from __future__ import annotations

"""Scaffold realtime pipeline orchestration for live frame processing.

The implementation here is intentionally minimal so the structured FastAPI app
can reserve a stable location for future realtime detector coordination without
copying logic from the legacy outer application.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RealtimePipeline:
    """Placeholder coordinator for future realtime frame-processing workflows.

    A later implementation can compose webcam readers, frame preprocessors,
    detectors, event sinks, and stream encoders behind this interface.
    """

    is_running: bool = False
    last_result: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Mark the pipeline as active.

        Future work can initialize detector state, background workers, and
        resource allocation here.
        """

        self.is_running = True

    def stop(self) -> None:
        """Mark the pipeline as inactive and clear transient runtime state."""

        self.is_running = False

    def process_frame(self, frame: Any) -> dict[str, Any]:
        """Accept a single frame and return placeholder processing metadata.

        Args:
            frame: Opaque frame data from a future webcam reader.

        Returns:
            A minimal payload describing that realtime processing is not yet
            implemented.
        """

        self.last_result = {
            "processed": False,
            "reason": "Realtime detection pipeline has not been implemented yet.",
            "frame_available": frame is not None,
        }
        return self.last_result
