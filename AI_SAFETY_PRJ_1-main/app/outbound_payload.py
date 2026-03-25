from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas import DetectionEvent, EventMetrics, EventStatus, EventType

MVP_OUTBOUND_EVENT_TYPES: tuple[EventType, ...] = (EventType.FALL, EventType.INACTIVE)


class OutboundDetectionEvent(BaseModel):
    """Canonical outbound event contract sent to Spring Boot.

    Notes:
    - This model intentionally supports only FALL/INACTIVE for MVP.
    - status is always normalized to PENDING at export time.
    """

    resident_id: int
    event_type: EventType
    status: EventStatus = EventStatus.PENDING
    detected_at: datetime
    snapshot_path: str
    description: str
    metrics: EventMetrics = Field(default_factory=EventMetrics)

    @classmethod
    def from_detection_event(cls, event: DetectionEvent) -> OutboundDetectionEvent | None:
        if event.event_type not in MVP_OUTBOUND_EVENT_TYPES:
            return None
        return cls(
            resident_id=event.resident_id,
            event_type=event.event_type,
            status=EventStatus.PENDING,
            detected_at=event.detected_at,
            snapshot_path=event.snapshot_path,
            description=event.description,
            metrics=event.metrics,
        )


def is_outbound_event_type_allowed(event_type: str) -> bool:
    normalized = event_type.strip().upper()
    if not normalized:
        return False
    return any(candidate.value == normalized for candidate in MVP_OUTBOUND_EVENT_TYPES)


def build_outbound_payload(
    event: DetectionEvent,
    *,
    sent_at: datetime,
    timezone_warning: str | None = None,
) -> dict[str, object] | None:
    outbound_event = OutboundDetectionEvent.from_detection_event(event)
    if outbound_event is None:
        return None

    payload: dict[str, object] = outbound_event.model_dump(mode="json")
    payload["sent_at"] = sent_at.isoformat()
    if timezone_warning:
        payload["timezone_warning"] = timezone_warning
    return payload
