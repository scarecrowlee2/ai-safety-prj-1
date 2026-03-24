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
class _FakeAnalysisSnapshot:
    frame_id: int | None
    timestamp_sec: float | None
    captured_at: datetime | None
    analyzed_at: datetime | None
    source_size: tuple[int, int] | None
    states: dict[str, bool]
    objects: list[dict[str, object]]
    banners: list[dict[str, object]]
    ready: bool
    box_coord_system: str
    message: str
    error: str | None = None


@dataclass
class _FakeAnalysisWorker:
    snapshot: _FakeAnalysisSnapshot

    def get_latest_snapshot(self) -> _FakeAnalysisSnapshot:
        return self.snapshot


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
    assert 'data-overlay-endpoint="/api/v1/realtime/overlay/latest"' in response.text


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


def test_realtime_overlay_latest_returns_ready_payload(monkeypatch) -> None:
    snapshot = _FakeAnalysisSnapshot(
        frame_id=42,
        timestamp_sec=3.25,
        captured_at=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
        analyzed_at=datetime(2026, 3, 24, 12, 0, 1, tzinfo=timezone.utc),
        source_size=(1280, 720),
        states={"fall": False},
        objects=[{"label": "person"}],
        banners=[{"level": "normal"}],
        ready=True,
        box_coord_system="normalized_xyxy",
        message="ok",
        error=None,
    )
    service = _FakeCaptureService(
        snapshot=None,
        status=SimpleNamespace(open_failed=False, last_error=None),
    )
    app = FastAPI()
    app.include_router(routes_realtime.api_router)
    client = TestClient(app)

    monkeypatch.setattr(routes_realtime, "get_realtime_analysis_worker", lambda: _FakeAnalysisWorker(snapshot))
    monkeypatch.setattr(routes_realtime, "get_realtime_capture_service", lambda: service)

    response = client.get("/api/v1/realtime/overlay/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["frame_id"] == 42
    assert payload["timestamp_sec"] == 3.25
    assert payload["captured_at"] == "2026-03-24T12:00:00+00:00"
    assert payload["analyzed_at"] == "2026-03-24T12:00:01+00:00"
    assert payload["source_size"] == {"width": 1280, "height": 720}
    assert payload["states"] == {"fall": False}
    assert payload["box_coord_system"] == "normalized_xyxy"
    assert payload["objects"] == [{"label": "person"}]
    assert payload["banners"] == [{"level": "normal"}]
    assert payload["message"] == "ok"
    assert payload["open_failed"] is False
    assert payload["error"] is None


def test_realtime_overlay_latest_returns_fallback_when_not_ready(monkeypatch) -> None:
    snapshot = _FakeAnalysisSnapshot(
        frame_id=None,
        timestamp_sec=None,
        captured_at=None,
        analyzed_at=None,
        source_size=None,
        states={},
        objects=[],
        banners=[],
        ready=False,
        box_coord_system="normalized_xyxy",
        message="Waiting for webcam frames.",
        error="camera offline",
    )
    service = _FakeCaptureService(
        snapshot=None,
        status=SimpleNamespace(open_failed=True, last_error="camera offline"),
    )
    app = FastAPI()
    app.include_router(routes_realtime.api_router)
    client = TestClient(app)

    monkeypatch.setattr(routes_realtime, "get_realtime_analysis_worker", lambda: _FakeAnalysisWorker(snapshot))
    monkeypatch.setattr(routes_realtime, "get_realtime_capture_service", lambda: service)

    response = client.get("/api/v1/realtime/overlay/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "ready": False,
        "frame_id": None,
        "timestamp_sec": None,
        "captured_at": None,
        "analyzed_at": None,
        "source_size": None,
        "states": {},
        "box_coord_system": "normalized_xyxy",
        "objects": [],
        "banners": [],
        "message": "Waiting for webcam frames.",
        "open_failed": True,
        "error": "camera offline",
    }
