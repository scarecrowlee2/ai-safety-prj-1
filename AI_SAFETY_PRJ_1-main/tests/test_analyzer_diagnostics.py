from __future__ import annotations

from app.core.analyzer import VideoAnalyzer
from app.detectors.fall import FallDetector
from app.detectors.inactive import InactiveDetector


def test_upload_analyzer_diagnostics_exposes_supported_and_unsupported_detectors(monkeypatch) -> None:
    def _fake_fall_load_model(self: FallDetector) -> None:
        self.landmarker = None
        self.hog = None
        self.enabled = True
        self.disabled_reason = ""
        self.backend = "test_backend"

    monkeypatch.setattr(FallDetector, "load_model", _fake_fall_load_model)
    monkeypatch.setattr(InactiveDetector, "init_background_subtractor", lambda self: object())

    analyzer = VideoAnalyzer()
    diagnostics = analyzer.diagnostics()

    assert diagnostics["capabilities"]["upload_supported_detectors"] == ["fall", "inactive"]
    assert diagnostics["capabilities"]["upload_unsupported_detectors"] == ["violence"]
    assert diagnostics["detectors"]["fall"]["supported"] is True
    assert diagnostics["detectors"]["inactive"]["supported"] is True
    assert diagnostics["detectors"]["violence"]["supported"] is False
    assert diagnostics["detectors"]["violence"]["mode"] == "unsupported"
