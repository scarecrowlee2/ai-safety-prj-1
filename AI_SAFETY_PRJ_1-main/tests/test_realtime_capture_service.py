from __future__ import annotations

from datetime import datetime, timezone
from time import sleep, time

import numpy as np

from app.core.realtime_capture import RealtimeCaptureService
from app.core.webcam_reader import WebcamConfig, WebcamFrame, WebcamOpenError


def _wait_for(predicate, timeout_sec: float = 1.0) -> bool:  # noqa: ANN001
    deadline = time() + timeout_sec
    while time() < deadline:
        if predicate():
            return True
        sleep(0.01)
    return False


class _FakeReaderSuccess:
    last_instance: _FakeReaderSuccess | None = None

    def __init__(self, _config: WebcamConfig) -> None:
        self.opened = False
        self.closed = False
        self.read_count = 0
        _FakeReaderSuccess.last_instance = self

    def open(self) -> None:
        self.opened = True

    def read_frame(self) -> WebcamFrame | None:
        self.read_count += 1
        if self.read_count == 1:
            image = np.zeros((8, 12, 3), dtype=np.uint8)
            return WebcamFrame(frame_index=7, timestamp_sec=1.25, image=image)
        return None

    def close(self) -> None:
        self.closed = True


class _FakeReaderOpenFail:
    last_instance: _FakeReaderOpenFail | None = None

    def __init__(self, _config: WebcamConfig) -> None:
        self.closed = False
        _FakeReaderOpenFail.last_instance = self

    def open(self) -> None:
        raise WebcamOpenError("camera offline")

    def close(self) -> None:
        self.closed = True


def test_realtime_capture_service_stores_latest_frame_snapshot(monkeypatch) -> None:
    from app.core import realtime_capture

    monkeypatch.setattr(realtime_capture, "WebcamReader", _FakeReaderSuccess)
    service = RealtimeCaptureService(WebcamConfig(source=0), read_fail_sleep_sec=0.01)

    service.start()
    assert _wait_for(lambda: service.get_latest_frame() is not None)

    snapshot = service.get_latest_frame()
    assert snapshot is not None
    assert snapshot.frame_id == 7
    assert snapshot.timestamp_sec == 1.25
    assert snapshot.source_size == (12, 8)
    assert snapshot.image.shape == (8, 12, 3)
    assert isinstance(snapshot.captured_at, datetime)
    assert snapshot.captured_at.tzinfo == timezone.utc

    status = service.get_status()
    assert status.open_failed is False
    assert status.frame_id == 7
    assert status.source_size == (12, 8)

    service.stop()
    assert service.is_running is False
    assert _FakeReaderSuccess.last_instance is not None
    assert _FakeReaderSuccess.last_instance.closed is True


def test_realtime_capture_service_reports_open_failure(monkeypatch) -> None:
    from app.core import realtime_capture

    monkeypatch.setattr(realtime_capture, "WebcamReader", _FakeReaderOpenFail)
    service = RealtimeCaptureService(WebcamConfig(source=1234), read_fail_sleep_sec=0.01)

    service.start()
    assert _wait_for(lambda: service.get_status().open_failed)

    status = service.get_status()
    assert status.running is False
    assert status.open_failed is True
    assert status.last_error is not None
    assert "camera offline" in status.last_error
    assert service.get_latest_frame() is None

    service.stop()
    assert service.is_running is False
    assert _FakeReaderOpenFail.last_instance is not None
    assert _FakeReaderOpenFail.last_instance.closed is True

class _FakeReaderSuccessThenFail:
    open_calls = 0

    def __init__(self, _config: WebcamConfig) -> None:
        self.closed = False
        self.read_count = 0

    def open(self) -> None:
        type(self).open_calls += 1
        if type(self).open_calls >= 2:
            raise WebcamOpenError("camera offline after restart")

    def read_frame(self) -> WebcamFrame | None:
        self.read_count += 1
        if self.read_count == 1:
            image = np.ones((6, 10, 3), dtype=np.uint8)
            return WebcamFrame(frame_index=1, timestamp_sec=0.5, image=image)
        return None

    def close(self) -> None:
        self.closed = True


def test_realtime_capture_service_clears_stale_frame_on_restart_failure(monkeypatch) -> None:
    from app.core import realtime_capture

    _FakeReaderSuccessThenFail.open_calls = 0
    monkeypatch.setattr(realtime_capture, "WebcamReader", _FakeReaderSuccessThenFail)
    service = RealtimeCaptureService(WebcamConfig(source=0), read_fail_sleep_sec=0.01)

    service.start()
    assert _wait_for(lambda: service.get_latest_frame() is not None)
    first_snapshot = service.get_latest_frame()
    assert first_snapshot is not None
    assert first_snapshot.frame_id == 1
    service.stop()

    service.start()
    # start() should clear stale frame immediately before new capture/open result.
    assert service.get_latest_frame() is None
    assert _wait_for(lambda: service.get_status().open_failed)
    assert service.get_latest_frame() is None

    service.stop()
