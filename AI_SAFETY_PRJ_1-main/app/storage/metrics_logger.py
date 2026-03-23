from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.timeutils import resolve_timezone


class MetricsLogger:
    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self) -> None:
        self.base_dir = settings.data_dir / "metrics"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.tz, self.timezone_warning = resolve_timezone(settings.app_timezone)

    # 이 메서드는 메트릭 로그를 파일 끝에 한 줄씩 추가합니다.
    def append(self, resident_id: int, stream_name: str, payload: dict) -> Path:
        now = datetime.now(self.tz)
        if self.timezone_warning and "timezone_warning" not in payload:
            payload = payload | {"timezone_warning": self.timezone_warning}
        file_path = self.base_dir / f"{now.strftime('%Y-%m-%d')}_{stream_name}_resident_{resident_id}.jsonl"
        with file_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return file_path
