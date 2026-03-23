from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path


# 이 메서드는 감지 이벤트를 JSONL 파일에 한 줄씩 기록하는 로거를 준비합니다.
class EventLogger:
    def __init__(self, log_path: str = "data/realtime_events.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # 이 메서드는 현재 UTC 시각을 ISO 문자열로 반환합니다.
    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # 이 메서드는 dataclass 또는 일반 객체를 직렬화 가능한 사전으로 변환합니다.
    def _serialize_payload(self, payload):
        if payload is None:
            return {}
        if is_dataclass(payload):
            return asdict(payload)
        if hasattr(payload, "__dict__"):
            return dict(payload.__dict__)
        return {"value": str(payload)}

    # 이 메서드는 감지 이벤트 한 건을 JSONL 로그 파일에 저장합니다.
    def log(self, event_type: str, payload, message: str, timestamp_sec: float | None = None):
        record = {
            "logged_at": self._now_iso(),
            "event_type": event_type,
            "message": message,
            "stream_timestamp_sec": timestamp_sec,
            "payload": self._serialize_payload(payload),
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
