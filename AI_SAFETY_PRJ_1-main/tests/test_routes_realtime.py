from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.realtime_capture import RealtimeFrameSnapshot
from app.api import routes_realtime


@dataclass
class _FakeCaptureService:
    snapshot: RealtimeFrameSnapshot | None
    status: object
    latest_frame_calls: int = 0

    def get_latest_frame(self) -> RealtimeFrameSnapshot | None:
        self.latest_frame_calls += 1
        return self.snapshot

    def get_status(self) -> object:
        return self.status


def test_realtime_dashboard_points_to_inner_video_route() -> None:
    app = FastAPI()
    app.include_router(routes_realtime.router)
    client = TestClient(app)

    response = client.get("/realtime")

    assert response.status_code == 200
    assert 'src="/realtime/video"' in response.text


def test_realtime_video_streams_latest_capture_frame(monkeypatch) -> None:
    snapshot = RealtimeFrameSnapshot(
        frame_id=10,
        timestamp_sec=2.5,
        captured_at=datetime.now(timezone.utc),
        source_size=(16, 12),
        image=np.zeros((12, 16, 3), dtype=np.uint8),
    )
    service = _FakeCaptureService(
        snapshot=snapshot,
        status=SimpleNamespace(open_failed=False, last_error=None),
    )

    monkeypatch.setattr(routes_realtime, "get_realtime_capture_service", lambda: service)
    monkeypatch.setattr(routes_realtime, "_encode_jpeg", lambda _image: b"jpeg-bytes")

    stream = routes_realtime._generate_webcam_stream()
    first_chunk = next(stream)
    stream.close()

    assert b"--frame" in first_chunk
    assert b"Content-Type: image/jpeg" in first_chunk
    assert b"jpeg-bytes" in first_chunk
    assert service.latest_frame_calls >= 1


def test_realtime_video_returns_fallback_frame_when_snapshot_missing(monkeypatch) -> None:
    captured_messages: list[str] = []
    service = _FakeCaptureService(
        snapshot=None,
        status=SimpleNamespace(open_failed=True, last_error="camera offline"),
    )

    monkeypatch.setattr(routes_realtime, "get_realtime_capture_service", lambda: service)
    monkeypatch.setattr(
        routes_realtime,
        "_build_status_frame",
        lambda message: captured_messages.append(message) or b"fallback-jpeg",
    )

    stream = routes_realtime._generate_webcam_stream()
    first_chunk = next(stream)
    stream.close()

    assert b"--frame" in first_chunk
    assert b"Content-Type: image/jpeg" in first_chunk
    assert b"fallback-jpeg" in first_chunk
    assert captured_messages
    assert "웹캠을 열 수 없습니다" in captured_messages[0]
