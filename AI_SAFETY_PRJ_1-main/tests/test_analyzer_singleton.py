from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _reset_shared_analyzer_state(monkeypatch) -> None:
    from app.core import analyzer as analyzer_module

    monkeypatch.setattr(analyzer_module, "_shared_analyzer", None)
    monkeypatch.setattr(analyzer_module, "_shared_analyzer_factory", None)


def test_get_video_analyzer_reuses_singleton_instance(monkeypatch) -> None:
    from app.core import analyzer as analyzer_module

    _reset_shared_analyzer_state(monkeypatch)

    class _StubAnalyzer:
        pass

    analyzer_first = analyzer_module.get_video_analyzer(factory=_StubAnalyzer)
    analyzer_second = analyzer_module.get_video_analyzer(factory=_StubAnalyzer)

    assert analyzer_first is analyzer_second


def test_health_endpoint_does_not_recreate_analyzer_on_repeated_calls(monkeypatch) -> None:
    from app.api import routes

    _reset_shared_analyzer_state(monkeypatch)

    created = {"count": 0}

    class _CountingAnalyzer:
        def __init__(self) -> None:
            created["count"] += 1

        def diagnostics(self) -> dict:
            return {
                "detectors": {
                    "fall": {"enabled": True},
                    "inactive": {"enabled": True, "mode": "full"},
                },
                "warnings": [],
            }

    monkeypatch.setattr(routes, "VideoAnalyzer", _CountingAnalyzer)

    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    response_first = client.get("/api/v1/health")
    response_second = client.get("/api/v1/health")

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json()["status"] == "ok"
    assert response_second.json()["status"] == "ok"
    assert created["count"] == 1
