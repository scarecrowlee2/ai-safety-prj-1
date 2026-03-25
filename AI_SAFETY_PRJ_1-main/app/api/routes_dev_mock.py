from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.notifier import EventNotifier
from app.storage.outbox_store import OutboxStore

router = APIRouter(prefix="/api/v1/dev/mock-receiver", tags=["dev-mock-receiver"])


class _MockEventStore:
    """In-memory receiver store for local/dev outbound verification only."""

    def __init__(self, maxlen: int = 200) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = Lock()

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        with self._lock:
            self._events.append(record)
        return record

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, limit)
        with self._lock:
            items = list(self._events)
        return items[-limit:]

    def clear(self) -> int:
        with self._lock:
            count = len(self._events)
            self._events.clear()
        return count

    def count(self) -> int:
        with self._lock:
            return len(self._events)


class MockReceiverIngestRequest(BaseModel):
    resident_id: int
    event_type: str
    status: str
    detected_at: str
    sent_at: str
    snapshot_path: str | None = None
    description: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


mock_receiver_store = _MockEventStore()


@router.post("/events")
def mock_receiver_events(payload: MockReceiverIngestRequest) -> dict[str, Any]:
    record = mock_receiver_store.append(payload.model_dump(mode="json"))
    return {
        "ok": True,
        "message": "dev mock receiver accepted payload",
        "received_at": record["received_at"],
        "received_count": mock_receiver_store.count(),
    }


@router.get("/events")
def mock_receiver_recent_events(limit: int = 20) -> dict[str, Any]:
    events = mock_receiver_store.recent(limit=limit)
    return {
        "items": events,
        "count": len(events),
        "total_received": mock_receiver_store.count(),
        "note": "dev/test only mock receiver history",
    }


@router.delete("/events")
def mock_receiver_clear_events() -> dict[str, Any]:
    removed = mock_receiver_store.clear()
    return {"ok": True, "removed": removed}


@router.get("/diagnostics")
def mock_receiver_diagnostics() -> dict[str, Any]:
    notifier = EventNotifier()
    return {
        "mock_receiver": {
            "enabled": True,
            "received_count": mock_receiver_store.count(),
        },
        "notifier": notifier.diagnostics(),
        "outbox": {
            "pending_count": OutboxStore().count(),
        },
        "note": "dev/test diagnostics endpoint only",
    }
