from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.core.config import settings
from app.schemas import CaptureRecord, DetectionEvent, EventMetrics, EventStatus, EventType


class EventStore:
    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self, sqlite_path: str | Path | None = None) -> None:
        self.sqlite_path = Path(sqlite_path or settings.sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # 이 메서드는 SQLite 데이터베이스 연결을 생성하고 반환합니다.
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    # 이 메서드는 이벤트 저장에 필요한 테이블을 초기화합니다.
    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resident_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    snapshot_path TEXT NOT NULL,
                    description TEXT NOT NULL,
                    metrics_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS capture_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events(id)
                );
                """
            )

    # 이 메서드는 이벤트와 캡처 기록을 데이터베이스에 저장합니다.
    def save_event(self, event: DetectionEvent, capture_record: CaptureRecord | None = None) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    resident_id, event_type, status, detected_at, snapshot_path, description, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.resident_id,
                    event.event_type.value,
                    event.status.value,
                    event.detected_at.isoformat(),
                    event.snapshot_path,
                    event.description,
                    event.metrics.model_dump_json(),
                ),
            )
            event_id = int(cursor.lastrowid)
            if capture_record is not None:
                conn.execute(
                    """
                    INSERT INTO capture_records (event_id, file_path, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        capture_record.file_path,
                        capture_record.created_at.isoformat(),
                        capture_record.expires_at.isoformat(),
                    ),
                )
            return event_id

    # 이 메서드는 저장된 이벤트 목록을 최신순으로 조회합니다.
    def list_events(self) -> list[DetectionEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT resident_id, event_type, status, detected_at, snapshot_path, description, metrics_json FROM events ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    # 이 메서드는 전송 실패 payload를 outbox 파일에 적재합니다.
    def append_outbox(self, payload: dict) -> None:
        settings.outbox_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with settings.outbox_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # 이 메서드는 데이터베이스 조회 결과 한 행을 DetectionEvent 객체로 변환합니다.
    def _row_to_event(self, row: sqlite3.Row) -> DetectionEvent:
        metrics_payload = json.loads(row["metrics_json"])
        return DetectionEvent(
            resident_id=row["resident_id"],
            event_type=EventType(row["event_type"]),
            status=EventStatus(row["status"]),
            detected_at=datetime.fromisoformat(row["detected_at"]),
            snapshot_path=row["snapshot_path"],
            description=row["description"],
            metrics=EventMetrics.model_validate(metrics_payload),
        )

    # 이 메서드는 여러 이벤트를 순차적으로 저장하고 ID 목록을 반환합니다.
    def bulk_save(self, events: Iterable[tuple[DetectionEvent, CaptureRecord | None]]) -> list[int]:
        saved_ids: list[int] = []
        for event, capture_record in events:
            saved_ids.append(self.save_event(event, capture_record))
        return saved_ids
