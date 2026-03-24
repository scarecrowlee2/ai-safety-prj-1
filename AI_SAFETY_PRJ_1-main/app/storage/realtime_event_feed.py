from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


class RealtimeEventFeed:
    """Lightweight JSONL-backed store for recent realtime dashboard events."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        self.log_path = Path(log_path) if log_path is not None else settings.realtime_event_log_path
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
