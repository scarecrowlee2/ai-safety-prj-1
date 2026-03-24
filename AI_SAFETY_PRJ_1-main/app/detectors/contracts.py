from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class DetectorInput:
    """Standard detector input payload used by realtime and upload flows."""

    frame: np.ndarray
    timestamp_sec: float
    context: dict[str, Any] | None = None


@dataclass(slots=True)
class OverlayAnnotation:
    """Optional overlay metadata emitted by detectors."""

    label: str
    color_bgr: tuple[int, int, int] | None = None
    box_xyxy: tuple[int, int, int, int] | None = None


@dataclass(slots=True)
class DetectorResult:
    """Normalized detector output for pipeline consumers."""

    detector: str
    event_type: str
    detected: bool
    label: str
    score: float | None = None
    overlays: list[OverlayAnnotation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_decision: Any = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("raw_decision", None)
        return payload
