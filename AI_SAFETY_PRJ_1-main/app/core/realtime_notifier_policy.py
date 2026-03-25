from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.timeutils import resolve_timezone
from app.notifier import EventNotifier
from app.outbound_payload import is_outbound_event_type_allowed
from app.schemas import DetectionEvent, EventMetrics, EventType


class RealtimeNotifierPolicy:
    """Policy helper that decides if realtime alerts are eligible for outbound notification.

    Realtime notification is intentionally opt-in so high-frequency webcam alerts do not
    generate external traffic by default.
    """

    def __init__(self) -> None:
        self.enabled = settings.realtime_notify_enabled
        self.allowed_event_types = {
            item.strip().lower()
            for item in settings.realtime_notify_event_types.split(",")
            if item.strip()
        }
        self.resident_id = settings.realtime_notify_resident_id
        self.tz, _ = resolve_timezone(settings.app_timezone)

    def should_notify(self, event_type: str) -> bool:
        if not self.enabled:
            return False
        normalized = event_type.strip().lower()
        if not normalized:
            return False
        if normalized not in self.allowed_event_types:
            return False
        return is_outbound_event_type_allowed(normalized)

    def to_detection_event(self, logged_event: dict[str, Any]) -> DetectionEvent | None:
        event_type_value = str(logged_event.get("event_type", "")).strip().lower()
        if not self.should_notify(event_type_value):
            return None

        event_type_map = {
            "fall": EventType.FALL,
            "inactive": EventType.INACTIVE,
            "violence": EventType.VIOLENCE,
        }
        mapped_type = event_type_map.get(event_type_value)
        if mapped_type is None:
            return None

        metadata = logged_event.get("metadata") if isinstance(logged_event.get("metadata"), dict) else {}
        confidence = logged_event.get("confidence")
        metrics = EventMetrics(notes=metadata)
        if isinstance(confidence, (int, float)):
            metrics.notes.setdefault("confidence", float(confidence))

        description = str(logged_event.get("label") or logged_event.get("message") or "Realtime alert detected")
        return DetectionEvent(
            resident_id=self.resident_id,
            event_type=mapped_type,
            detected_at=datetime.now(self.tz),
            # TODO(phase2): replace virtual stream URI with persisted snapshot file path.
            snapshot_path="realtime://stream",
            description=description,
            metrics=metrics,
        )


class RealtimeNotifierIntegration:
    """Single integration boundary for optional realtime->notifier delivery."""

    def __init__(self, notifier: EventNotifier, policy: RealtimeNotifierPolicy | None = None) -> None:
        self.notifier = notifier
        self.policy = policy or RealtimeNotifierPolicy()

    def notify_logged_events(self, logged_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not logged_events:
            return []

        results: list[dict[str, Any]] = []
        for logged_event in logged_events:
            detection_event = self.policy.to_detection_event(logged_event)
            if detection_event is None:
                continue
            try:
                result = self.notifier.send_event(detection_event)
            except Exception as exc:
                results.append(
                    {
                        "event_type": logged_event.get("event_type"),
                        "success": False,
                        "attempts": 1,
                        "detail": str(exc),
                        "disposition": "failed_queued",
                    }
                )
                continue

            results.append(
                {
                    "event_type": logged_event.get("event_type"),
                    "success": result.success,
                    "attempts": result.attempts,
                    "detail": result.detail,
                    "disposition": result.disposition.value,
                }
            )
        return results
