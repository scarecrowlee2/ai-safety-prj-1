from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.detectors import fall as fall_module
from app.detectors.fall import FallDetector


class _LandmarkerStub:
    def __init__(self) -> None:
        self.timestamps: list[int] = []

    def detect_for_video(self, _mp_image, timestamp_ms: int):
        if self.timestamps and timestamp_ms <= self.timestamps[-1]:
            raise ValueError("Input timestamp must be monotonically increasing.")
        self.timestamps.append(timestamp_ms)
        landmark = SimpleNamespace(x=0.5, y=0.5, z=0.0, visibility=1.0, presence=1.0)
        return SimpleNamespace(pose_landmarks=[[landmark] * 33])


class _CV2Stub:
    COLOR_BGR2RGB = 0

    @staticmethod
    def cvtColor(frame, _code):
        return frame


class _MPStub:
    class ImageFormat:
        SRGB = 0

    class Image:
        def __init__(self, image_format, data) -> None:
            self.image_format = image_format
            self.data = data


def test_extract_keypoints_enforces_monotonic_mediapipe_timestamps(monkeypatch) -> None:
    detector = FallDetector()
    detector.backend = "mediapipe_tasks"
    detector.landmarker = _LandmarkerStub()

    monkeypatch.setattr(fall_module, "cv2", _CV2Stub())
    monkeypatch.setattr(fall_module, "mp", _MPStub())

    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    detector.extract_keypoints(frame, 1000)
    detector.extract_keypoints(frame, 1000)
    detector.extract_keypoints(frame, 999)

    assert detector.landmarker.timestamps == [1000, 1001, 1002]
