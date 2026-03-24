from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@dataclass
class _DummyAnalyzeResult:
    payload: dict

    def model_dump(self, mode: str = "json") -> dict:
        return self.payload


class _DummyAnalyzer:
    def diagnostics(self) -> dict:
        return {
            "capabilities": {
                "upload_supported_detectors": ["fall", "inactive"],
                "upload_unsupported_detectors": ["violence"],
            },
            "detectors": {
                "fall": {"enabled": False},
                "inactive": {"enabled": False},
                "violence": {"enabled": False, "mode": "unsupported"},
            }
        }

    def analyze_video(self, resident_id: int, video_path) -> _DummyAnalyzeResult:  # noqa: ANN001
        return _DummyAnalyzeResult(
            {
                "resident_id": resident_id,
                "events": [],
                "meta": {"video_path": str(video_path)},
            }
        )


def test_app_import_and_root_route_smoke() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["docs"] == "/docs"
    assert body["health"] == "/api/v1/health"


def test_health_endpoint_smoke(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes, "VideoAnalyzer", _DummyAnalyzer)
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == settings.app_name
    assert "detectors" in body
    assert body["feature_scope"]["upload_analyzer_supported_detectors"] == ["fall", "inactive"]
    assert body["feature_scope"]["upload_analyzer_unsupported_detectors"] == ["violence"]


def test_realtime_events_endpoint_smoke(monkeypatch) -> None:
    from app.api import routes_realtime

    fake_events = [{"event_type": "fall", "timestamp": "2026-03-24T00:00:00Z"}]
    monkeypatch.setattr(routes_realtime, "_load_recent_events", lambda limit=6: fake_events[:limit])
    client = TestClient(app)

    response = client.get("/api/v1/realtime/events?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["events"] == fake_events
    assert body["items"] == fake_events
    assert body["log_path"]


def test_analyze_video_route_requires_form_fields() -> None:
    client = TestClient(app)

    response = client.post("/api/v1/analyze/video")

    assert response.status_code == 422


def test_analyze_video_route_smoke(monkeypatch, tmp_path) -> None:
    from app.api import routes

    monkeypatch.setattr(routes, "VideoAnalyzer", _DummyAnalyzer)
    tmp_upload_dir = tmp_path / "uploads"
    tmp_upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(routes.settings, "temp_upload_dir", tmp_upload_dir)
    client = TestClient(app)

    response = client.post(
        "/api/v1/analyze/video",
        data={"resident_id": "7", "notify": "false"},
        files={"video": ("clip.mp4", b"fake-video-bytes", "video/mp4")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resident_id"] == 7
    assert body["events"] == []


def test_settings_paths_are_initialized() -> None:
    assert settings.temp_upload_dir.exists()
    assert settings.realtime_event_log_path.parent.exists()
