from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from app.storage.realtime_event_feed import RealtimeEventFeed
from app.storage.realtime_event_store import RealtimeEventStore


class EventLogger:
    """Backward-compatible logger wrapper used by realtime processing."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        feed = RealtimeEventFeed(log_path)
        self.store = RealtimeEventStore(feed=feed)

    def log(self, event_type: str, payload: Any, message: str, timestamp_sec: float | None = None) -> dict[str, Any]:
        metadata = self._serialize_payload(payload)
        confidence = self._extract_confidence(metadata)
        return self.store.record_event(
            event_type=event_type,
            label=message,
            timestamp_sec=timestamp_sec,
            confidence=confidence,
            metadata=metadata,
        )

    def list_recent(self, limit: int) -> list[dict[str, Any]]:
        return self.store.list_recent_feed(limit)

    @staticmethod
    def _serialize_payload(payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "__dict__"):
            return dict(payload.__dict__)
        return {"value": str(payload)}

    @staticmethod
    def _extract_confidence(payload: dict[str, Any]) -> float | None:
        for key in ("confidence", "score", "probability"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None


__all__ = ["EventLogger", "RealtimeEventFeed", "RealtimeEventStore"]
