from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.api import routes_dev_mock
from app.core.realtime_notifier_policy import RealtimeNotifierIntegration, RealtimeNotifierPolicy
from app.notifier import EventNotifier
from app.schemas import DetectionEvent, EventMetrics, EventStatus, EventType
from app.storage.event_store import EventStore
from app.storage.outbox_store import OutboxStore


class _FailingResponse:
    def raise_for_status(self) -> None:
        raise RuntimeError("mock network down")


class _FailingClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, json: dict[str, object]):  # noqa: ARG002
        return _FailingResponse()


class _InprocessClient:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, json: dict[str, object]):
        path = url.replace("http://testserver", "")
        response = self._client.post(path, json=json)

        class _Resp:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise RuntimeError(f"status {self.status_code}")

        return _Resp(response.status_code)


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch, tmp_path):  # noqa: ANN001
    test_app = FastAPI()
    test_app.include_router(routes_dev_mock.router)

    monkeypatch.setattr("app.notifier.settings.retry_max_attempts", 1)
    monkeypatch.setattr("app.notifier.settings.retry_backoff_seconds", 0.0)
    monkeypatch.setattr("app.notifier.settings.spring_boot_delivery_enabled", True)
    monkeypatch.setattr("app.notifier.settings.outbox_jsonl", tmp_path / "outbox.jsonl")
    routes_dev_mock.mock_receiver_store.clear()

    with TestClient(test_app) as client:
        yield client, test_app

    routes_dev_mock.mock_receiver_store.clear()


def _wire_inprocess_httpx(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr("app.notifier.httpx.Client", lambda timeout: _InprocessClient(client))


def test_upload_style_outbound_payload_reaches_mock_receiver(monkeypatch: pytest.MonkeyPatch, mock_client) -> None:  # noqa: ANN001
    client, test_app = mock_client
    _wire_inprocess_httpx(monkeypatch, client)
    monkeypatch.setattr("app.notifier.settings.spring_boot_event_url", "http://testserver/api/v1/dev/mock-receiver/events")

    event = DetectionEvent(
        resident_id=77,
        event_type=EventType.FALL,
        status=EventStatus.CONFIRMED,
        detected_at=datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc),
        snapshot_path="data/snapshots/upload-fall.jpg",
        description="fall detected from upload",
        metrics=EventMetrics(horizontal_seconds=6.1),
    )

    result = EventNotifier(EventStore(), OutboxStore()).send_event(event)

    assert result.success is True
    assert result.disposition.value == "delivered"
    mock_events = client.get("/api/v1/dev/mock-receiver/events").json()["items"]
    assert len(mock_events) == 1
    payload = mock_events[0]["payload"]
    assert payload["resident_id"] == 77
    assert payload["event_type"] == "FALL"
    assert payload["status"] == "PENDING"
    assert payload["snapshot_path"] == "data/snapshots/upload-fall.jpg"
    assert "sent_at" in payload


def test_realtime_fall_inactive_delivered_violence_not_delivered(monkeypatch: pytest.MonkeyPatch, mock_client) -> None:  # noqa: ANN001
    client, test_app = mock_client
    _wire_inprocess_httpx(monkeypatch, client)
    monkeypatch.setattr("app.notifier.settings.spring_boot_event_url", "http://testserver/api/v1/dev/mock-receiver/events")
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_enabled", True)
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_event_types", "fall,inactive,violence")
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_resident_id", 55)

    integration = RealtimeNotifierIntegration(
        notifier=EventNotifier(EventStore(), OutboxStore()),
        policy=RealtimeNotifierPolicy(),
    )
    frame = np.zeros((4, 4, 3), dtype=np.uint8)

    results = integration.notify_logged_events(
        [
            {"event_type": "fall", "label": "fall", "logged_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "inactive", "label": "inactive", "logged_at": datetime.now(timezone.utc).isoformat()},
            {"event_type": "violence", "label": "violence", "logged_at": datetime.now(timezone.utc).isoformat()},
        ],
        frame=frame,
    )

    assert len(results) == 2
    mock_events = client.get("/api/v1/dev/mock-receiver/events").json()["items"]
    event_types = [item["payload"]["event_type"] for item in mock_events]
    assert event_types == ["FALL", "INACTIVE"]


def test_failed_send_queued_then_retry_reaches_mock_receiver(monkeypatch: pytest.MonkeyPatch, mock_client) -> None:  # noqa: ANN001
    client, test_app = mock_client
    monkeypatch.setattr("app.notifier.settings.spring_boot_event_url", "http://testserver/api/v1/dev/mock-receiver/events")
    monkeypatch.setattr("app.notifier.httpx.Client", lambda timeout: _FailingClient())

    notifier = EventNotifier(EventStore(), OutboxStore())
    event = DetectionEvent(
        resident_id=88,
        event_type=EventType.FALL,
        status=EventStatus.CONFIRMED,
        detected_at=datetime(2026, 3, 25, 10, 0, tzinfo=timezone.utc),
        snapshot_path="data/snapshots/fail-first.jpg",
        description="fall",
        metrics=EventMetrics(),
    )
    send_result = notifier.send_event(event)

    assert send_result.success is False
    assert send_result.disposition.value == "failed_queued"
    assert OutboxStore().count() == 1

    _wire_inprocess_httpx(monkeypatch, client)
    summary = notifier.retry_send()

    assert summary == {"retried": 1, "succeeded": 1, "failed": 0}
    mock_events = client.get("/api/v1/dev/mock-receiver/events").json()["items"]
    assert len(mock_events) == 1
    assert mock_events[0]["payload"]["resident_id"] == 88
    assert OutboxStore().count() == 0
