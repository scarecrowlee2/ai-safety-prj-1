from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.storage.realtime_event_feed import RealtimeEventFeed


class RealtimeEventStore:
    """Storage boundary for realtime events.

    - JSONL feed: fast, lightweight recent-event source for the realtime dashboard.
    - SQLite table: durable inner-project persistence for realtime event history.
    """

    def __init__(
        self,
        *,
        feed: RealtimeEventFeed | None = None,
        sqlite_path: str | Path | None = None,
    ) -> None:
        self.feed = feed or RealtimeEventFeed()
        self.sqlite_path = Path(sqlite_path or settings.sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def record_event(
        self,
        *,
        event_type: str,
        label: str,
        timestamp_sec: float | None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = self.feed.record_event(
            event_type=event_type,
            label=label,
            timestamp_sec=timestamp_sec,
            confidence=confidence,
            metadata=metadata,
        )

        # Keep dashboard feed availability as the priority; durable persistence is best-effort.
        with suppress(sqlite3.Error, OSError, ValueError, TypeError):
            self._save_durable(event)

        return event

    def list_recent_feed(self, limit: int) -> list[dict[str, Any]]:
        return self.feed.list_recent(limit)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS realtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logged_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    message TEXT NOT NULL,
                    stream_timestamp_sec REAL,
                    confidence REAL,
                    metadata_json TEXT NOT NULL
                )
                """
            )

    def _save_durable(self, event: dict[str, Any]) -> None:
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO realtime_events (
                    logged_at,
                    event_type,
                    label,
                    message,
                    stream_timestamp_sec,
                    confidence,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("logged_at") or "",
                    event.get("event_type") or "unknown",
                    event.get("label") or "",
                    event.get("message") or event.get("label") or "",
                    event.get("stream_timestamp_sec"),
                    event.get("confidence"),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
