from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    FALL = "FALL"
    INACTIVE = "INACTIVE"
    VIOLENCE = "VIOLENCE"


class EventStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CLOSED = "CLOSED"


class EventMetrics(BaseModel):
    torso_angle_from_vertical_deg: float | None = None
    horizontal_seconds: float | None = None
    pose_confidence: float | None = None
    bbox_aspect_ratio: float | None = None
    motion_ratio: float | None = None
    inactive_seconds: float | None = None
    num_persons: int | None = None
    notes: dict[str, Any] = Field(default_factory=dict)


class DetectionEvent(BaseModel):
    resident_id: int
    event_type: EventType
    status: EventStatus = EventStatus.PENDING
    detected_at: datetime
    snapshot_path: str
    description: str
    metrics: EventMetrics = Field(default_factory=EventMetrics)


class AnalyzeVideoResponse(BaseModel):
    resident_id: int
    video_name: str
    events: list[DetectionEvent]
    warnings: list[str] = Field(default_factory=list)


class NotificationDisposition(str, Enum):
    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED_QUEUED = "failed_queued"
    SKIPPED = "skipped"


class NotificationResult(BaseModel):
    success: bool
    attempts: int = 1
    detail: str = ""
    disposition: NotificationDisposition = NotificationDisposition.DELIVERED


class CaptureRecord(BaseModel):
    event_id: int | None = None
    file_path: str
    created_at: datetime
    expires_at: datetime


class FeatureFrame(BaseModel):
    timestamp_sec: float
    person_present: bool = False
    motion_ratio: float = 0.0
    pose_confidence: float = 0.0
    torso_angle_from_vertical_deg: float | None = None
    bbox_aspect_ratio: float | None = None
    num_persons: int = 0
