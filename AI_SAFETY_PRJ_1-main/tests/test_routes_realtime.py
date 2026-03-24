from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from fastapi.testclient import TestClient

from app.core.webcam_reader import WebcamOpenError
from app.main import app


@dataclass
class _DummyFrame:
    image: np.ndarray


@dataclass
class _FakeRealtimeResult:
    frame: np.ndarray
    metadata: dict[str, object]


class _FakeRealtimePipeline:
    def process_frame(self, image: np.ndarray, _timestamp_sec: float) -> _FakeRealtimeResult:
        return _FakeRealtimeResult(frame=image, metadata={"new_logged_events": []})


class _StreamingReader:
    def __init__(self, _config) -> None:
        self.fps = 30.0
        self.closed = False

    def open(self) -> None:
        return None

    def frames(self):
        yield _DummyFrame(image=np.zeros((12, 12, 3), dtype=np.uint8))

    def close(self) -> None:
        self.closed = True


class _UnavailableReader:
    def __init__(self, _config) -> None:
        self.fps = 30.0

    def open(self) -> None:
        raise WebcamOpenError("camera offline")

    def close(self) -> None:
        return None


def test_realtime_dashboard_points_to_inner_video_route() -> None:
    client = TestClient(app)

    response = client.get("/realtime")

    assert response.status_code == 200
    assert 'src="/realtime/video"' in response.text


def test_realtime_video_streams_mjpeg_frames(monkeypatch) -> None:
    from app.api import routes_realtime

    monkeypatch.setattr(routes_realtime, "WebcamReader", _StreamingReader)
    monkeypatch.setattr(routes_realtime, "get_realtime_pipeline", lambda: _FakeRealtimePipeline())
    monkeypatch.setattr(routes_realtime, "_encode_jpeg", lambda _image: b"jpeg-bytes")
    client = TestClient(app)

    with client.stream("GET", "/realtime/video") as response:
        first_chunk = next(response.iter_bytes())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert b"--frame" in first_chunk
    assert b"Content-Type: image/jpeg" in first_chunk


def test_realtime_video_returns_fallback_frame_when_camera_is_unavailable(monkeypatch) -> None:
    from app.api import routes_realtime

    monkeypatch.setattr(routes_realtime, "WebcamReader", _UnavailableReader)
    monkeypatch.setattr(routes_realtime, "_build_status_frame", lambda _message: b"fallback-jpeg")
    client = TestClient(app)

    with client.stream("GET", "/realtime/video") as response:
        first_chunk = next(response.iter_bytes())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert b"--frame" in first_chunk
    assert b"Content-Type: image/jpeg" in first_chunk
