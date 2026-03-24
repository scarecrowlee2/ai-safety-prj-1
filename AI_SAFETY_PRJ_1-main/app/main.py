from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.routes_realtime import api_router as realtime_api_router
from app.api.routes_realtime import router as realtime_router
from app.core.analyzer import get_video_analyzer
from app.core.config import settings
from app.core.realtime_analysis_registry import get_realtime_analysis_worker
from app.core.realtime_capture_registry import get_realtime_capture_service


def _run_startup_initialization() -> None:
    """
    Fail fast in production-style configuration:
    if ENABLE_YOLO_PERSON_GATE=true, InactiveDetector initialization must succeed.
    """
    get_video_analyzer()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _run_startup_initialization()
    capture_service = get_realtime_capture_service()
    analysis_worker = get_realtime_analysis_worker()
    capture_service.start()
    analysis_worker.start()
    try:
        yield
    finally:
        analysis_worker.stop()
        capture_service.stop()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.include_router(router)
app.include_router(realtime_router)
app.include_router(realtime_api_router)


# 이 함수는 루트 경로에서 기본 서비스 정보를 반환합니다.
@app.get("/")
def root() -> dict:
    return {
        "message": "AI 스마트 생활안전 서비스 MVP - Python Detector",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
