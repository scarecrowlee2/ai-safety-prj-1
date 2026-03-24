from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import sleep, time

import numpy as np

from app.core.realtime_analysis_worker import RealtimeAnalysisWorker
from app.core.realtime_capture import RealtimeFrameSnapshot


@dataclass
class _FakeCaptureStatus:
    open_failed: bool = False
    last_error: str | None = None


class _FakeCaptureService:
    def __init__(self) -> None:
        self._status = _FakeCaptureStatus()
        self._snapshot: RealtimeFrameSnapshot | None = None

    def get_status(self) -> _FakeCaptureStatus:
        return self._status

    def get_latest_frame(self) -> RealtimeFrameSnapshot | None:
        return self._snapshot

    def set_snapshot(self, snapshot: RealtimeFrameSnapshot | None) -> None:
        self._snapshot = snapshot

    def set_open_failed(self, error: str) -> None:
        self._status = _FakeCaptureStatus(open_failed=True, last_error=error)


class _FakePipeline:
    def __init__(self) -> None:
        self.analyzed_frame_ids: list[int | str | None] = []

    def analyze_frame(self, *, frame, timestamp_sec: float, frame_id: int | str | None):  # noqa: ANN001
        self.analyzed_frame_ids.append(frame_id)
        return {
            "overlay_payload": {
                "states": {"fall_alert": False, "violence_watch": True},
                "objects": [{"label": f"obj-{frame_id}"}],
                "banners": [{"text": f"banner-{frame_id}", "level": "watch"}],
            }
        }


def _wait_until(predicate, timeout_sec: float = 1.2) -> bool:  # noqa: ANN001
    deadline = time() + timeout_sec
    while time() < deadline:
        if predicate():
            return True
        sleep(0.01)
    return False


def test_worker_analyzes_only_new_frame_id_and_updates_latest_snapshot() -> None:
    capture = _FakeCaptureService()
    pipeline = _FakePipeline()
    worker = RealtimeAnalysisWorker(capture_service=capture, pipeline=pipeline, target_fps=200.0, idle_sleep_sec=0.01)

    frame1 = RealtimeFrameSnapshot(
        frame_id=1,
        timestamp_sec=1.0,
        captured_at=datetime.now(timezone.utc),
        source_size=(8, 6),
        image=np.zeros((6, 8, 3), dtype=np.uint8),
    )

    worker.start()
    try:
        capture.set_snapshot(frame1)
        assert _wait_until(lambda: len(pipeline.analyzed_frame_ids) >= 1)

        sleep(0.06)
        assert pipeline.analyzed_frame_ids.count(1) == 1

        frame2 = RealtimeFrameSnapshot(
            frame_id=2,
            timestamp_sec=2.0,
            captured_at=datetime.now(timezone.utc),
            source_size=(8, 6),
            image=np.zeros((6, 8, 3), dtype=np.uint8),
        )
        capture.set_snapshot(frame2)
        assert _wait_until(lambda: pipeline.analyzed_frame_ids.count(2) == 1)

        snapshot = worker.get_latest_snapshot()
        assert snapshot.ready is True
        assert snapshot.frame_id == 2
        assert snapshot.states == {"fall_alert": False, "violence_watch": True}
        assert snapshot.objects == [{"label": "obj-2"}]
        assert snapshot.banners == [{"text": "banner-2", "level": "watch"}]
        assert snapshot.message == "ok"
    finally:
        worker.stop()


def test_worker_survives_missing_frame_and_open_failed_state() -> None:
    capture = _FakeCaptureService()
    pipeline = _FakePipeline()
    worker = RealtimeAnalysisWorker(capture_service=capture, pipeline=pipeline, target_fps=120.0, idle_sleep_sec=0.01)

    worker.start()
    try:
        assert _wait_until(lambda: worker.get_latest_snapshot().ready is False)
        initial = worker.get_latest_snapshot()
        assert initial.message in {"Waiting for webcam frames.", "Analysis worker not started."}

        capture.set_open_failed("camera offline")
        capture.set_snapshot(None)

        assert _wait_until(lambda: worker.get_latest_snapshot().message == "Webcam unavailable for analysis.")
        failed = worker.get_latest_snapshot()
        assert failed.ready is False
        assert failed.error == "camera offline"
        assert pipeline.analyzed_frame_ids == []
    finally:
        worker.stop()
