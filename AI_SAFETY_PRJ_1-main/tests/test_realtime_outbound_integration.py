from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from app.core.realtime_notifier_policy import RealtimeNotifierIntegration, RealtimeNotifierPolicy
from app.schemas import NotificationDisposition, NotificationResult


class _DummyNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent_events = []

    def send_event(self, event):  # noqa: ANN001
        if self.fail:
            raise RuntimeError("network down")
        self.sent_events.append(event)
        return NotificationResult(success=True, attempts=1, disposition=NotificationDisposition.DELIVERED, detail="ok")


class _DummySnapshotStorage:
    def __init__(self, tmp_path, *, fail: bool = False) -> None:  # noqa: ANN001
        self.base = tmp_path
        self.fail = fail

    def save(self, frame, resident_id, event_type, detected_at):  # noqa: ANN001
        if self.fail:
            raise RuntimeError("save failed")
        path = self.base / f"{event_type.value.lower()}_{resident_id}.jpg"
        path.write_bytes(frame.tobytes())

        class _Record:
            file_path = str(path)

        return _Record()


def _build_policy(monkeypatch: pytest.MonkeyPatch) -> RealtimeNotifierPolicy:
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_enabled", True)
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_event_types", "fall,inactive,violence")
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_resident_id", 11)
    return RealtimeNotifierPolicy()


def test_realtime_fall_and_inactive_trigger_outbound(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    policy = _build_policy(monkeypatch)
    notifier = _DummyNotifier()
    integration = RealtimeNotifierIntegration(
        notifier=notifier,
        policy=policy,
        snapshot_storage=_DummySnapshotStorage(tmp_path),
    )

    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    events = [
        {"event_type": "fall", "label": "fall", "logged_at": datetime.now(timezone.utc).isoformat()},
        {"event_type": "inactive", "label": "inactive", "logged_at": datetime.now(timezone.utc).isoformat()},
    ]
    results = integration.notify_logged_events(events, frame=frame)

    assert len(results) == 2
    assert len(notifier.sent_events) == 2
    assert notifier.sent_events[0].event_type.value == "FALL"
    assert notifier.sent_events[1].event_type.value == "INACTIVE"
    assert notifier.sent_events[0].snapshot_path.endswith("fall_11.jpg")


def test_realtime_violence_stays_internal(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    policy = _build_policy(monkeypatch)
    notifier = _DummyNotifier()
    integration = RealtimeNotifierIntegration(
        notifier=notifier,
        policy=policy,
        snapshot_storage=_DummySnapshotStorage(tmp_path),
    )

    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    results = integration.notify_logged_events([
        {"event_type": "violence", "label": "violence", "logged_at": datetime.now(timezone.utc).isoformat()}
    ], frame=frame)

    assert results == []
    assert notifier.sent_events == []


def test_realtime_notifier_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    policy = _build_policy(monkeypatch)
    integration = RealtimeNotifierIntegration(
        notifier=_DummyNotifier(fail=True),
        policy=policy,
        snapshot_storage=_DummySnapshotStorage(tmp_path),
    )

    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    results = integration.notify_logged_events([
        {"event_type": "fall", "label": "fall", "logged_at": datetime.now(timezone.utc).isoformat()}
    ], frame=frame)

    assert len(results) == 1
    assert results[0]["success"] is False


def test_realtime_missing_resident_id_skips(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_enabled", True)
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_event_types", "fall,inactive")
    monkeypatch.setattr("app.core.realtime_notifier_policy.settings.realtime_notify_resident_id", None)
    policy = RealtimeNotifierPolicy()
    notifier = _DummyNotifier()
    integration = RealtimeNotifierIntegration(
        notifier=notifier,
        policy=policy,
        snapshot_storage=_DummySnapshotStorage(tmp_path),
    )

    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    results = integration.notify_logged_events([
        {"event_type": "fall", "label": "fall", "logged_at": datetime.now(timezone.utc).isoformat()}
    ], frame=frame)

    assert len(results) == 1
    assert results[0]["disposition"] == "skipped"
    assert notifier.sent_events == []
