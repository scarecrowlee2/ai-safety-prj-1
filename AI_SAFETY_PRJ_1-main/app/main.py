from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.2.0")
app.include_router(router)


# 이 함수는 루트 경로에서 기본 서비스 정보를 반환합니다.
@app.get("/")
def root() -> dict:
    return {
        "message": "AI 스마트 생활안전 서비스 MVP - Python Detector",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
