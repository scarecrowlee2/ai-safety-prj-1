from __future__ import annotations

from datetime import datetime

from app.core.realtime_notifier_policy import RealtimeNotifierPolicy
from app.outbound_payload import build_outbound_payload
from app.schemas import DetectionEvent, EventMetrics, EventStatus, EventType


def _event(event_type: EventType, *, status: EventStatus = EventStatus.CONFIRMED) -> DetectionEvent:
    return DetectionEvent(
        resident_id=7,
        event_type=event_type,
        status=status,
        detected_at=datetime.fromisoformat("2026-03-25T08:00:00+00:00"),
        snapshot_path="data/snapshots/e1.jpg",
        description="detected",
        metrics=EventMetrics(notes={"source": "test"}),
    )


def test_upload_event_payload_allows_fall_and_inactive_with_pending_status() -> None:
    sent_at = datetime.fromisoformat("2026-03-25T08:05:00+00:00")

    fall_payload = build_outbound_payload(_event(EventType.FALL), sent_at=sent_at)
    inactive_payload = build_outbound_payload(_event(EventType.INACTIVE), sent_at=sent_at)

    assert fall_payload is not None
    assert inactive_payload is not None
    assert fall_payload["event_type"] == "FALL"
    assert inactive_payload["event_type"] == "INACTIVE"
    assert fall_payload["status"] == "PENDING"
    assert inactive_payload["status"] == "PENDING"


def test_upload_event_payload_excludes_violence() -> None:
    payload = build_outbound_payload(
        _event(EventType.VIOLENCE),
        sent_at=datetime.fromisoformat("2026-03-25T08:05:00+00:00"),
    )
    assert payload is None


def test_realtime_logged_event_mapping_uses_same_outbound_rules(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_enabled", True)
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_event_types", "fall,inactive,violence")
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_resident_id", 99)

    policy = RealtimeNotifierPolicy()

    fall_event = policy.to_detection_event({"event_type": "fall", "label": "fall alert"})
    inactive_event = policy.to_detection_event({"event_type": "inactive", "label": "inactive alert"})
    violence_event = policy.to_detection_event({"event_type": "violence", "label": "violence alert"})

    assert fall_event is not None
    assert inactive_event is not None
    assert violence_event is None
    assert fall_event.status == EventStatus.PENDING
    assert inactive_event.status == EventStatus.PENDING
    assert fall_event.snapshot_path == "realtime://stream"
