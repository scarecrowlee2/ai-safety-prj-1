from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RealtimeEventFeed:
    """Lightweight JSONL-backed store for recent realtime dashboard events."""

    def __init__(self, log_path: str = "data/realtime_events.jsonl") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_event(
        self,
        *,
        event_type: str,
        label: str,
        timestamp_sec: float | None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "label": label,
            "message": label,
            "stream_timestamp_sec": timestamp_sec,
            "confidence": confidence,
            "metadata": metadata or {},
        }

        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

        return event

    def list_recent(self, limit: int) -> list[dict[str, Any]]:
        if limit <= 0 or not self.log_path.exists():
            return []

        recent_lines: deque[str] = deque(maxlen=limit)
        with self.log_path.open("r", encoding="utf-8") as file:
            for line in file:
                stripped = line.strip()
                if stripped:
                    recent_lines.append(stripped)

        events: list[dict[str, Any]] = []
        for raw_line in reversed(recent_lines):
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if not isinstance(parsed, dict):
                continue

            events.append(self._normalize(parsed))

        return events

    def _normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = record.get("payload")
        if isinstance(payload, dict):
            metadata = payload
        else:
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}

        label = record.get("label") or record.get("message") or "이벤트 정보가 없습니다."

        return {
            "event_type": record.get("event_type", "unknown"),
            "label": label,
            "message": record.get("message") or label,
            "logged_at": record.get("logged_at"),
            "stream_timestamp_sec": record.get("stream_timestamp_sec"),
            "confidence": self._coerce_float(record.get("confidence")),
            "metadata": metadata,
        }

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None


class EventLogger:
    """Backward-compatible logger wrapper used by realtime processing."""

    def __init__(self, log_path: str = "data/realtime_events.jsonl") -> None:
        self.feed = RealtimeEventFeed(log_path)

    def log(self, event_type: str, payload: Any, message: str, timestamp_sec: float | None = None) -> dict[str, Any]:
        metadata = self._serialize_payload(payload)
        confidence = self._extract_confidence(metadata)

        return self.feed.record_event(
            event_type=event_type,
            label=message,
            timestamp_sec=timestamp_sec,
            confidence=confidence,
            metadata=metadata,
        )

    def list_recent(self, limit: int) -> list[dict[str, Any]]:
        return self.feed.list_recent(limit)

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
