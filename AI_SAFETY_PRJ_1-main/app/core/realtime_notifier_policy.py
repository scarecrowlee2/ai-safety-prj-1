from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

import numpy as np

from app.core.config import settings
from app.core.timeutils import resolve_timezone
from app.notifier import EventNotifier
from app.outbound_payload import is_outbound_event_type_allowed
from app.schemas import DetectionEvent, EventMetrics, EventType
from app.storage.snapshots import SnapshotStorage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RealtimeOutboundResult:
    event_type: str
    delivered: bool
    disposition: str
    detail: str


class RealtimeNotifierPolicy:
    """Policy helper that decides if realtime alerts are eligible for outbound notification."""

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

    def has_resident_id(self) -> bool:
        return self.resident_id is not None

    def to_detection_event(
        self,
        logged_event: dict[str, Any],
        *,
        snapshot_path: str,
    ) -> DetectionEvent | None:
        event_type_value = str(logged_event.get("event_type", "")).strip().lower()
        if not self.should_notify(event_type_value):
            return None
        if self.resident_id is None:
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
        detected_at = self.resolve_detected_at(logged_event)
        return DetectionEvent(
            resident_id=self.resident_id,
            event_type=mapped_type,
            detected_at=detected_at,
            snapshot_path=snapshot_path,
            description=description,
            metrics=metrics,
        )

    def resolve_detected_at(self, logged_event: dict[str, Any]) -> datetime:
        raw_logged_at = logged_event.get("logged_at")
        if isinstance(raw_logged_at, str) and raw_logged_at:
            try:
                return datetime.fromisoformat(raw_logged_at.replace("Z", "+00:00")).astimezone(self.tz)
            except ValueError:
                pass
        return datetime.now(self.tz)


class RealtimeNotifierIntegration:
    """Single integration boundary for realtime event -> outbound notifier delivery."""

    def __init__(
        self,
        notifier: EventNotifier,
        policy: RealtimeNotifierPolicy | None = None,
        snapshot_storage: SnapshotStorage | None = None,
    ) -> None:
        self.notifier = notifier
        self.policy = policy or RealtimeNotifierPolicy()
        self.snapshot_storage = snapshot_storage or SnapshotStorage(base_dir=settings.realtime_snapshot_dir)
        self._last_attempt_at: str | None = None
        self._last_success: bool | None = None
        self._last_error: str | None = None

    def notify_logged_events(
        self,
        logged_events: list[dict[str, Any]],
        *,
        frame: np.ndarray | None = None,
    ) -> list[dict[str, Any]]:
        if not logged_events:
            return []

        results: list[dict[str, Any]] = []
        for logged_event in logged_events:
            event_type = str(logged_event.get("event_type", "")).strip().lower()
            if not self.policy.should_notify(event_type):
                continue

            detected_at = self.policy.resolve_detected_at(logged_event)
            snapshot_path = self._resolve_snapshot_path(
                frame=frame,
                event_type=event_type,
                detected_at=detected_at,
            )
            detection_event = self.policy.to_detection_event(logged_event, snapshot_path=snapshot_path)
            if detection_event is None:
                if self.policy.has_resident_id():
                    continue
                detail = "realtime resident_id missing - outbound skipped"
                logger.warning(detail)
                self._record_diagnostics(success=False, detail=detail)
                results.append(
                    {
                        "event_type": logged_event.get("event_type"),
                        "success": False,
                        "attempts": 0,
                        "detail": detail,
                        "disposition": "skipped",
                    }
                )
                continue

            self._last_attempt_at = datetime.now().isoformat()
            try:
                result = self.notifier.send_event(detection_event)
            except Exception as exc:
                detail = str(exc)
                logger.exception("Realtime outbound notifier failed.")
                self._record_diagnostics(success=False, detail=detail)
                results.append(
                    {
                        "event_type": logged_event.get("event_type"),
                        "success": False,
                        "attempts": 1,
                        "detail": detail,
                        "disposition": "failed_queued",
                    }
                )
                continue

            self._record_diagnostics(success=result.success, detail=result.detail)
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

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": self.policy.enabled,
            "allowed_event_types": sorted(self.policy.allowed_event_types),
            "resident_id": self.policy.resident_id,
            "resident_id_mode": "single-fixed-config",
            "last_attempt_at": self._last_attempt_at,
            "last_success": self._last_success,
            "last_error": self._last_error,
        }

    def _resolve_snapshot_path(self, *, frame: np.ndarray | None, event_type: str, detected_at: datetime) -> str:
        if frame is None:
            return "realtime://stream"

        if self.policy.resident_id is None:
            return "realtime://stream"

        event_map = {
            "fall": EventType.FALL,
            "inactive": EventType.INACTIVE,
            "violence": EventType.VIOLENCE,
        }
        mapped_event_type = event_map.get(event_type)
        if mapped_event_type is None:
            return "realtime://stream"

        try:
            record = self.snapshot_storage.save(
                frame=frame,
                resident_id=self.policy.resident_id,
                event_type=mapped_event_type,
                detected_at=detected_at,
            )
            return record.file_path
        except Exception as exc:  # noqa: BLE001
            logger.warning("Realtime snapshot save failed, fallback to virtual path: %s", exc)
            return "realtime://stream"

    def _record_diagnostics(self, *, success: bool, detail: str) -> None:
        self._last_success = success
        self._last_error = None if success else detail
