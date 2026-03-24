from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.routes_realtime import api_router as realtime_api_router
from app.api.routes_realtime import router as realtime_router
from app.core.config import settings
from app.detectors.inactive import InactiveDetector

app = FastAPI(title=settings.app_name, version="0.2.0")
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.include_router(router)
app.include_router(realtime_router)
app.include_router(realtime_api_router)


@app.on_event("startup")
def validate_inactive_detector_runtime() -> None:
    """
    Fail fast in production-style configuration:
    if ENABLE_YOLO_PERSON_GATE=true, InactiveDetector initialization must succeed.
    """
    InactiveDetector()


# 이 함수는 루트 경로에서 기본 서비스 정보를 반환합니다.
@app.get("/")
def root() -> dict:
    return {
        "message": "AI 스마트 생활안전 서비스 MVP - Python Detector",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
