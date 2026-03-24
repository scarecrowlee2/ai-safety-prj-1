from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.detectors.inactive import InactiveDetector
from app.main import app


@pytest.fixture(autouse=True)
def reset_person_gate_cache() -> None:
    InactiveDetector._person_gate_model_name = None
    InactiveDetector._person_gate_instance = None
    InactiveDetector._person_gate_init_error = None


def test_inactive_status_is_degraded_when_person_gate_is_disabled(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "enable_yolo_person_gate", False)
    monkeypatch.setattr(InactiveDetector, "init_background_subtractor", lambda self: object())

    detector = InactiveDetector()
    status = detector.status()

    assert status["enabled"] is True
    assert status["person_gate_enabled"] is False
    assert status["person_gate_ready"] is False
    assert status["mode"] == "degraded"


def test_inactive_status_is_full_when_person_gate_is_enabled_and_ready(monkeypatch) -> None:
    from app.core.config import settings

    class FakeYOLO:
        def __init__(self, _model_name: str) -> None:
            pass

        def predict(self, _frame, verbose: bool = False):
            return []

    monkeypatch.setattr(settings, "enable_yolo_person_gate", True)
    monkeypatch.setattr(InactiveDetector, "init_background_subtractor", lambda self: object())
    monkeypatch.setattr("app.detectors.inactive.YOLO", FakeYOLO)

    detector = InactiveDetector()
    status = detector.status()

    assert status["enabled"] is True
    assert status["person_gate_enabled"] is True
    assert status["person_gate_ready"] is True
    assert status["mode"] == "full"


def test_inactive_status_mode_resolution_covers_error_and_disabled() -> None:
    detector = InactiveDetector.__new__(InactiveDetector)
    detector.person_gate_backend = "ultralytics_yolo"
    detector.disabled_reason = ""
    detector._yolo = None

    detector.enabled = True
    detector.person_gate_enabled = True
    detector.person_gate_ready = False
    detector.mode = detector._resolve_mode()
    assert detector.status()["mode"] == "error"

    detector.enabled = False
    detector.person_gate_enabled = True
    detector.person_gate_ready = False
    detector.mode = detector._resolve_mode()
    assert detector.status()["mode"] == "disabled"


def test_person_gate_required_failure_raises_runtime_error(monkeypatch) -> None:
    from app.core.config import settings

    class BrokenYOLO:
        def __init__(self, _model_name: str) -> None:
            raise RuntimeError("yolo init failed")

    monkeypatch.setattr(settings, "enable_yolo_person_gate", True)
    monkeypatch.setattr(InactiveDetector, "init_background_subtractor", lambda self: object())
    monkeypatch.setattr("app.detectors.inactive.YOLO", BrokenYOLO)

    with pytest.raises(RuntimeError, match="failed to initialize"):
        InactiveDetector()


@pytest.mark.parametrize(
    ("inactive_mode", "expected_service_status"),
    [
        ("full", "ok"),
        ("degraded", "degraded"),
        ("error", "degraded"),
        ("disabled", "degraded"),
    ],
)
def test_health_reflects_inactive_mode(monkeypatch, inactive_mode: str, expected_service_status: str) -> None:
    from app.api import routes

    class _Analyzer:
        def diagnostics(self) -> dict:
            return {
                "detectors": {
                    "fall": {"enabled": True},
                    "inactive": {"mode": inactive_mode, "enabled": True},
                }
            }

    monkeypatch.setattr(routes, "get_video_analyzer", lambda: _Analyzer())
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_service_status
    assert body["detectors"]["inactive"]["mode"] == inactive_mode


def test_startup_fails_fast_when_required_person_gate_is_not_ready(monkeypatch) -> None:
    from app import main

    monkeypatch.setattr(main, "get_video_analyzer", lambda: (_ for _ in ()).throw(RuntimeError("gate init failed")))

    with pytest.raises(RuntimeError, match="gate init failed"):
        with TestClient(app):
            pass
