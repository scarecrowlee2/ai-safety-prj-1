from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.schemas import DetectionEvent, EventMetrics, EventType
from app.storage.event_store import EventStore


# 이 테스트는 이벤트 저장과 조회가 정상 동작하는지 검증합니다.
def test_event_store_save_and_list(tmp_path: Path) -> None:
    db_path = tmp_path / "events.db"
    store = EventStore(db_path)

    event = DetectionEvent(
        resident_id=1,
        event_type=EventType.FALL,
        detected_at=datetime.fromisoformat("2026-03-21T14:58:12+09:00"),
        snapshot_path="data/snapshots/demo.jpg",
        description="horizontal posture sustained",
        metrics=EventMetrics(torso_angle_from_vertical_deg=72.1, horizontal_seconds=6.2),
    )

    event_id = store.save_event(event)
    assert event_id >= 1

    events = store.list_events()
    assert len(events) == 1
    assert events[0].resident_id == 1
    assert events[0].event_type == EventType.FALL
    assert events[0].metrics.horizontal_seconds == 6.2
