from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from app.core.realtime_capture import RealtimeFrameSnapshot


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


def test_generate_webcam_stream_yields_mjpeg_chunk_from_latest_snapshot(monkeypatch) -> None:
    from app.api import routes_realtime

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


def test_generate_webcam_stream_yields_fallback_chunk_without_snapshot(monkeypatch) -> None:
    from app.api import routes_realtime

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
