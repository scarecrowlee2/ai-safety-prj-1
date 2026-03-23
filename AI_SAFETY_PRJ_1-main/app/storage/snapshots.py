from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings
from app.core.timeutils import resolve_timezone
from app.schemas import CaptureRecord, EventType


class SnapshotStorage:
    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self) -> None:
        self.base_dir = settings.snapshot_dir
        self.tz, self.timezone_warning = resolve_timezone(settings.app_timezone)

    # 이 메서드는 스냅샷 이미지를 저장하고 저장 기록을 반환합니다.
    def save(self, frame: np.ndarray, resident_id: int, event_type: EventType, detected_at: datetime) -> CaptureRecord:
        local_time = detected_at.astimezone(self.tz)
        day_dir = self.base_dir / local_time.strftime("%Y-%m-%d") / f"resident_{resident_id}"
        day_dir.mkdir(parents=True, exist_ok=True)

        file_name = f"{event_type.value}_{local_time.strftime('%H%M%S_%f')}.jpg"
        file_path = day_dir / file_name
        ok = cv2.imwrite(str(file_path), frame)
        if not ok:
            raise RuntimeError(f"스냅샷 저장에 실패했습니다: {file_path}")

        expires_at = local_time + timedelta(days=settings.snapshot_expire_days)
        return CaptureRecord(
            file_path=str(file_path),
            created_at=local_time,
            expires_at=expires_at,
        )

    # 이 메서드는 보관 기간이 지난 스냅샷 파일을 정리합니다.
    def cleanup_expired(self, now: datetime | None = None) -> int:
        now = now or datetime.now(self.tz)
        deleted = 0
        for path in self.base_dir.rglob("*.jpg"):
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=self.tz)
                if mtime + timedelta(days=settings.snapshot_expire_days) < now:
                    path.unlink(missing_ok=True)
                    deleted += 1
            except FileNotFoundError:
                continue
        return deleted
