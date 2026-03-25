from __future__ import annotations

import asyncio
import json
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
    assert 'data-overlay-stream-endpoint="/api/v1/realtime/overlay/stream"' in response.text


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
    assert isinstance(payload["server_now"], str)
    assert payload["source_size"] == {"width": 1280, "height": 720}
    assert payload["states"] == {"fall": False}
    assert payload["box_coord_system"] == "normalized_xyxy"
    assert payload["objects"] == [{"label": "person"}]
    assert payload["banners"] == [{"level": "normal"}]
    assert payload["analysis_seq"] is None
    assert isinstance(payload["overlay_age_ms"], int)
    assert payload["overlay_stale_threshold_ms"] >= 0
    assert isinstance(payload["is_stale"], bool)
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
    assert payload["ready"] is False
    assert payload["frame_id"] is None
    assert payload["timestamp_sec"] is None
    assert payload["captured_at"] is None
    assert payload["analyzed_at"] is None
    assert isinstance(payload["server_now"], str)
    assert payload["source_size"] is None
    assert payload["states"] == {}
    assert payload["box_coord_system"] == "normalized_xyxy"
    assert payload["objects"] == []
    assert payload["banners"] == []
    assert payload["analysis_seq"] is None
    assert payload["overlay_age_ms"] is None
    assert payload["overlay_stale_threshold_ms"] >= 0
    assert payload["is_stale"] is False
    assert payload["message"] == "Waiting for webcam frames."
    assert payload["open_failed"] is True
    assert payload["error"] == "camera offline"


def test_realtime_diagnostics_returns_capture_analysis_overlay_state(monkeypatch) -> None:
    snapshot = _FakeAnalysisSnapshot(
        frame_id=55,
        timestamp_sec=10.0,
        captured_at=datetime(2026, 3, 24, 12, 2, tzinfo=timezone.utc),
        analyzed_at=datetime(2026, 3, 24, 12, 2, 1, tzinfo=timezone.utc),
        source_size=(640, 480),
        states={},
        objects=[],
        banners=[],
        ready=True,
        box_coord_system="normalized_xyxy",
        message="ok",
        error=None,
    )
    service = _FakeCaptureService(
        snapshot=None,
        status=SimpleNamespace(
            running=True,
            open_failed=False,
            last_error=None,
            frame_id=54,
            last_frame_at=datetime(2026, 3, 24, 12, 2, tzinfo=timezone.utc),
        ),
    )
    app = FastAPI()
    app.include_router(routes_realtime.api_router)
    client = TestClient(app)

    monkeypatch.setattr(routes_realtime, "get_realtime_capture_service", lambda: service)
    monkeypatch.setattr(
        routes_realtime,
        "get_realtime_analysis_worker",
        lambda: SimpleNamespace(is_running=True, get_latest_snapshot=lambda: snapshot),
    )
    monkeypatch.setattr(routes_realtime.realtime_notifier, "diagnostics", lambda: {"enabled": True, "last_success": True})

    response = client.get("/api/v1/realtime/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["capture"]["running"] is True
    assert payload["capture"]["open_failed"] is False
    assert payload["capture"]["last_error"] is None
    assert payload["capture"]["latest_frame"]["frame_id"] == 54
    assert payload["capture"]["latest_frame"]["captured_at"] == "2026-03-24T12:02:00+00:00"
    assert payload["analysis"]["running"] is True
    assert payload["analysis"]["latest_frame"]["frame_id"] == 55
    assert payload["analysis"]["latest_frame"]["analyzed_at"] == "2026-03-24T12:02:01+00:00"
    assert payload["overlay"]["transport_recommended_mode"] == "sse"
    assert payload["outbound"] == {"enabled": True, "last_success": True}
    assert isinstance(payload["server_now"], str)


class _FakeRequest:
    def __init__(self) -> None:
        self._checks = 0

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > 1


def test_realtime_overlay_stream_returns_sse_event(monkeypatch) -> None:
    snapshot = _FakeAnalysisSnapshot(
        frame_id=99,
        timestamp_sec=4.2,
        captured_at=datetime(2026, 3, 24, 12, 1, tzinfo=timezone.utc),
        analyzed_at=datetime(2026, 3, 24, 12, 1, 1, tzinfo=timezone.utc),
        source_size=(640, 360),
        states={"fall": False},
        objects=[{"label": "person"}],
        banners=[],
        ready=True,
        box_coord_system="normalized_xyxy",
        message="ok",
        error=None,
    )
    service = _FakeCaptureService(
        snapshot=None,
        status=SimpleNamespace(open_failed=False, last_error=None),
    )
    monkeypatch.setattr(routes_realtime, "get_realtime_analysis_worker", lambda: _FakeAnalysisWorker(snapshot))
    monkeypatch.setattr(routes_realtime, "get_realtime_capture_service", lambda: service)
    request = _FakeRequest()

    async def _read_first_event() -> str:
        stream = routes_realtime._generate_overlay_event_stream(request)
        try:
            return await stream.__anext__()
        finally:
            await stream.aclose()

    event = asyncio.run(_read_first_event())

    assert event.startswith("event: overlay\n")
    assert event.endswith("\n\n")
    assert "data: " in event

    data_line = next(line for line in event.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["ready"] is True
    assert payload["frame_id"] == 99
    assert payload["box_coord_system"] == "normalized_xyxy"
    assert payload["overlay_stale_threshold_ms"] >= 0
    assert isinstance(payload["is_stale"], bool)
    assert payload["objects"] == [{"label": "person"}]



def test_realtime_overlay_latest_uses_default_box_coord_system_when_missing() -> None:
    snapshot = SimpleNamespace(
        frame_id=None,
        timestamp_sec=None,
        captured_at=None,
        analyzed_at=None,
        source_size=None,
        states={},
        objects=[],
        banners=[],
        ready=False,
        message="waiting",
        error=None,
    )
    payload = routes_realtime._build_overlay_payload(
        snapshot=snapshot,
        capture_status=SimpleNamespace(open_failed=False),
    )

    assert payload["box_coord_system"] == routes_realtime.BOX_COORD_SYSTEM_NORMALIZED_XYXY
    assert payload["overlay_age_ms"] is None
    assert payload["is_stale"] is False
