from __future__ import annotations

from app.core.webcam_reader import WebcamConfig, WebcamReader


class _FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5

    class error(Exception):
        pass


class _FakeCapture:
    def __init__(self, *, raise_on_height: bool = False, reject_width: bool = False) -> None:
        self.raise_on_height = raise_on_height
        self.reject_width = reject_width
        self.calls: list[tuple[int, float]] = []

    def set(self, property_id: int, value: float) -> bool:
        self.calls.append((property_id, value))
        if self.raise_on_height and property_id == _FakeCv2.CAP_PROP_FRAME_HEIGHT:
            raise _FakeCv2.error("height setting failed")
        if self.reject_width and property_id == _FakeCv2.CAP_PROP_FRAME_WIDTH:
            return False
        return True


def test_apply_capture_settings_is_best_effort_when_property_set_raises(monkeypatch, caplog) -> None:
    monkeypatch.setattr(WebcamReader, "_cv2", staticmethod(lambda: _FakeCv2))
    reader = WebcamReader(WebcamConfig(width=640, height=480, fps=24))
    capture = _FakeCapture(raise_on_height=True)

    reader._apply_capture_settings(capture)

    assert capture.calls == [
        (_FakeCv2.CAP_PROP_FRAME_WIDTH, 640.0),
        (_FakeCv2.CAP_PROP_FRAME_HEIGHT, 480.0),
        (_FakeCv2.CAP_PROP_FPS, 24.0),
    ]
    assert "could not be applied" in caplog.text


def test_apply_capture_settings_warns_when_property_rejected(monkeypatch, caplog) -> None:
    monkeypatch.setattr(WebcamReader, "_cv2", staticmethod(lambda: _FakeCv2))
    reader = WebcamReader(WebcamConfig(width=1280, height=720))
    capture = _FakeCapture(reject_width=True)

    reader._apply_capture_settings(capture)

    assert capture.calls == [
        (_FakeCv2.CAP_PROP_FRAME_WIDTH, 1280.0),
        (_FakeCv2.CAP_PROP_FRAME_HEIGHT, 720.0),
    ]
    assert "was rejected by backend" in caplog.text
