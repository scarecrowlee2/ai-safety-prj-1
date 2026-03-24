from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.realtime_pipeline import RealtimePipeline
from app.detectors.contracts import DetectorResult, OverlayAnnotation
from app.detectors.fall import FallDecision
from app.detectors.inactive import InactiveDecision
from app.detectors.violence import ViolenceDecision


@dataclass
class _FakeEventLogger:
    calls: int = 0

    def log(self, event_type, decision, message, timestamp_sec):  # noqa: ANN001
        self.calls += 1
        return {
            "event_type": event_type,
            "message": message,
            "timestamp_sec": timestamp_sec,
        }


class _NoopDetector:
    pass


class _FakeCv2:
    FONT_HERSHEY_SIMPLEX = 0

    def __init__(self) -> None:
        self.rectangles: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int, int], int]] = []
        self.texts: list[str] = []

    def rectangle(self, _img, p1, p2, color, thickness):  # noqa: ANN001
        self.rectangles.append((p1, p2, color, thickness))

    def putText(self, _img, text, _org, _font, _scale, _color, _thickness):  # noqa: ANN001, N802
        self.texts.append(text)


def _build_pipeline(monkeypatch) -> RealtimePipeline:
    monkeypatch.setattr("app.core.realtime_pipeline.FallDetector", _NoopDetector)
    monkeypatch.setattr("app.core.realtime_pipeline.InactiveDetector", _NoopDetector)
    monkeypatch.setattr("app.core.realtime_pipeline.ViolenceDetector", lambda **_kwargs: _NoopDetector())
    return RealtimePipeline(event_logger=_FakeEventLogger())


def test_analyze_frame_returns_expected_overlay_payload_shape(monkeypatch) -> None:
    pipeline = _build_pipeline(monkeypatch)

    fall_decision = FallDecision(
        is_candidate=True,
        pose_confidence=0.91,
        torso_angle_from_vertical_deg=70.0,
        bbox_aspect_ratio=1.4,
        horizontal_seconds=0.4,
    )
    inactive_decision = InactiveDecision(
        motion_ratio=0.01,
        person_present=True,
        inactive_seconds=1.7,
        num_persons=1,
        should_alert=False,
        bbox=(10, 20, 30, 40),
    )
    violence_decision = ViolenceDecision(
        num_persons=2,
        motion_ratio=0.13,
        close_pairs=1,
        suspicious_seconds=0.9,
        should_alert=False,
        boxes=[(16, 12, 20, 10)],
    )

    monkeypatch.setattr(
        "app.core.realtime_pipeline.run_fall_detector",
        lambda *_args, **_kwargs: DetectorResult(
            detector="fall",
            event_type="fall",
            detected=False,
            label="FALL_WATCH",
            score=0.91,
            raw_decision=fall_decision,
        ),
    )
    monkeypatch.setattr(
        "app.core.realtime_pipeline.run_inactive_detector",
        lambda *_args, **_kwargs: DetectorResult(
            detector="inactive",
            event_type="inactive",
            detected=False,
            label="INACTIVE_WATCH",
            score=0.99,
            raw_decision=inactive_decision,
        ),
    )
    monkeypatch.setattr(
        "app.core.realtime_pipeline.run_violence_detector",
        lambda *_args, **_kwargs: DetectorResult(
            detector="violence",
            event_type="violence",
            detected=False,
            label="VIOLENCE_WATCH",
            score=0.13,
            raw_decision=violence_decision,
            overlays=[OverlayAnnotation(label="P1", box_xyxy=(16, 12, 36, 22), color_bgr=(1, 2, 3))],
        ),
    )

    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    result = pipeline.analyze_frame(frame=frame, timestamp_sec=10.0, frame_id=77)

    payload = result["overlay_payload"]
    assert payload["frame_id"] == 77
    assert payload["timestamp_sec"] == 10.0
    assert payload["source_size"] == {"width": 64, "height": 48}
    assert payload["box_coord_system"] == "normalized_xyxy"
    assert set(payload["states"]) == {
        "fall_alert",
        "fall_watch",
        "inactive_alert",
        "inactive_watch",
        "violence_alert",
        "violence_watch",
    }
    assert isinstance(payload["status_lines"], list)
    assert len(payload["status_lines"]) == 3
    assert payload["objects"][0]["label"] == "P1"
    assert payload["objects"][0]["box"]["x1"] == 0.25
    assert payload["objects"][0]["box"]["y1"] == 0.25
    assert payload["banners"] == []


def test_render_overlay_draws_using_payload_objects(monkeypatch) -> None:
    pipeline = _build_pipeline(monkeypatch)
    fake_cv2 = _FakeCv2()
    monkeypatch.setattr(pipeline, "_get_cv2", lambda: fake_cv2)
    monkeypatch.setattr(pipeline, "_draw_status_panel", lambda _overlay: (20, 30, 10))

    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    overlay_payload = {
        "states": {"violence_alert": False},
        "status_lines": [{"text": "status-line", "color_bgr": [10, 20, 30]}],
        "objects": [
            {
                "label": "obj-1",
                "box": {"x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.5},
                "style": {"color_bgr": [1, 2, 3], "thickness": 4},
            }
        ],
        "banners": [{"text": "banner-text", "level": "violence_alert"}],
        "source_size": {"width": 200, "height": 100},
        "box_coord_system": "normalized_xyxy",
    }

    rendered = pipeline.render_overlay(frame=frame, overlay_payload=overlay_payload)

    assert rendered.shape == frame.shape
    assert any(entry[0] == (20, 20) and entry[1] == (80, 50) for entry in fake_cv2.rectangles)
    assert "status-line" in fake_cv2.texts
    assert "obj-1" in fake_cv2.texts
    assert "banner-text" in fake_cv2.texts


def test_process_frame_remains_backward_compatible(monkeypatch) -> None:
    pipeline = _build_pipeline(monkeypatch)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    expected_payload = {"states": {"fall_alert": False}, "objects": [], "banners": []}
    expected_metadata = {"events": [], "states": {"fall_alert": False}}
    expected_overlay = np.ones_like(frame)

    monkeypatch.setattr(
        pipeline,
        "analyze_frame",
        lambda **_kwargs: {"overlay_payload": expected_payload, "metadata": expected_metadata},
    )
    monkeypatch.setattr(pipeline, "render_overlay", lambda **_kwargs: expected_overlay)

    result = pipeline.process_frame(frame=frame, timestamp_sec=1.0)

    assert np.array_equal(result.frame, expected_overlay)
    assert result.metadata == expected_metadata
