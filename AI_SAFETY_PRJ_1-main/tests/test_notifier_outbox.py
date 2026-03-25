from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.core.config import settings
from app.notifier import EventNotifier
from app.schemas import DetectionEvent, EventMetrics, EventStatus, EventType
from app.storage.event_store import EventStore
from app.storage.outbox_store import OutboxStore


class _DummyResponse:
    def __init__(self, should_fail: bool) -> None:
        self.should_fail = should_fail

    def raise_for_status(self) -> None:
        if self.should_fail:
            raise RuntimeError("boom")


class _DummyClient:
    def __init__(self, outcomes: list[bool]) -> None:
        self._outcomes = outcomes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, json: dict[str, object]):
        should_fail = self._outcomes.pop(0)
        return _DummyResponse(should_fail=should_fail)


@pytest.fixture
def event() -> DetectionEvent:
    return DetectionEvent(
        resident_id=1,
        event_type=EventType.FALL,
        status=EventStatus.CONFIRMED,
        detected_at=datetime.fromisoformat("2026-03-21T14:58:12+09:00"),
        snapshot_path="data/snapshots/demo.jpg",
        description="fall detected",
        metrics=EventMetrics(horizontal_seconds=6.2),
    )


def _wire_settings(monkeypatch: pytest.MonkeyPatch, outbox_path: Path) -> None:
    monkeypatch.setattr(settings, "outbox_jsonl", outbox_path)
    monkeypatch.setattr(settings, "retry_backoff_seconds", 0.0)
    monkeypatch.setattr(settings, "retry_max_attempts", 3)
    monkeypatch.setattr(settings, "spring_boot_delivery_enabled", True)


def test_send_event_queues_when_url_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event: DetectionEvent) -> None:
    outbox_path = tmp_path / "outbox.jsonl"
    _wire_settings(monkeypatch, outbox_path)
    monkeypatch.setattr(settings, "spring_boot_event_url", "")

    notifier = EventNotifier(EventStore(tmp_path / "events.db"), OutboxStore(outbox_path))
    result = notifier.send_event(event)

    assert result.success is True
    assert result.disposition.value == "queued"

    lines = outbox_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["reason"] == "url_missing"
    assert record["payload"]["event_type"] == "FALL"


def test_send_event_success_does_not_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event: DetectionEvent) -> None:
    outbox_path = tmp_path / "outbox.jsonl"
    _wire_settings(monkeypatch, outbox_path)
    monkeypatch.setattr(settings, "spring_boot_event_url", "http://example.com/events")

    outcomes = [False]
    monkeypatch.setattr("app.notifier.httpx.Client", lambda timeout: _DummyClient(outcomes))

    notifier = EventNotifier(EventStore(tmp_path / "events.db"), OutboxStore(outbox_path))
    result = notifier.send_event(event)

    assert result.success is True
    assert result.disposition.value == "delivered"
    assert not outbox_path.exists() or outbox_path.read_text(encoding="utf-8") == ""


def test_send_event_failure_after_retry_queues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event: DetectionEvent) -> None:
    outbox_path = tmp_path / "outbox.jsonl"
    _wire_settings(monkeypatch, outbox_path)
    monkeypatch.setattr(settings, "spring_boot_event_url", "http://example.com/events")
    monkeypatch.setattr(settings, "retry_max_attempts", 2)

    outcomes = [True, True]
    monkeypatch.setattr("app.notifier.httpx.Client", lambda timeout: _DummyClient(outcomes))

    notifier = EventNotifier(EventStore(tmp_path / "events.db"), OutboxStore(outbox_path))
    result = notifier.send_event(event)

    assert result.success is False
    assert result.disposition.value == "failed_queued"
    record = json.loads(outbox_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["reason"] == "delivery_failed"
    assert "boom" in record["last_error"]


def test_retry_send_keeps_failed_and_removes_succeeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, event: DetectionEvent) -> None:
    outbox_path = tmp_path / "outbox.jsonl"
    _wire_settings(monkeypatch, outbox_path)
    monkeypatch.setattr(settings, "spring_boot_event_url", "http://example.com/events")
    monkeypatch.setattr(settings, "retry_max_attempts", 1)

    payload = {
        "resident_id": event.resident_id,
        "event_type": "FALL",
        "status": "PENDING",
        "detected_at": event.detected_at.isoformat(),
        "snapshot_path": event.snapshot_path,
        "description": event.description,
        "metrics": event.metrics.model_dump(mode="json"),
        "sent_at": "2026-03-21T14:59:00+09:00",
    }
    outbox_path.write_text(
        "\n".join(
            [
                json.dumps({"payload": payload, "queued_at": "2026-03-25T00:00:00+00:00", "source": "notify", "reason": "delivery_failed"}),
                json.dumps({"payload": payload | {"description": "second"}, "queued_at": "2026-03-25T00:00:01+00:00", "source": "notify", "reason": "delivery_failed"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    outcomes = [False, True]
    monkeypatch.setattr("app.notifier.httpx.Client", lambda timeout: _DummyClient(outcomes))

    notifier = EventNotifier(EventStore(tmp_path / "events.db"), OutboxStore(outbox_path))
    summary = notifier.retry_send()

    assert summary == {"retried": 2, "succeeded": 1, "failed": 1}
    remaining = [json.loads(line) for line in outbox_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(remaining) == 1
    assert remaining[0]["payload"]["description"] == "second"


def test_retry_send_survives_broken_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outbox_path = tmp_path / "outbox.jsonl"
    _wire_settings(monkeypatch, outbox_path)
    monkeypatch.setattr(settings, "spring_boot_event_url", "http://example.com/events")

    outbox_path.write_text("{not-json}\n", encoding="utf-8")

    notifier = EventNotifier(EventStore(tmp_path / "events.db"), OutboxStore(outbox_path))
    summary = notifier.retry_send()

    assert summary == {"retried": 1, "succeeded": 0, "failed": 1}
    line = outbox_path.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["reason"] == "retry_record_invalid"
