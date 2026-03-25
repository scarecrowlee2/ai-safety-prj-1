from __future__ import annotations

import json
import time
from datetime import datetime

import httpx

from app.core.config import settings
from app.core.timeutils import resolve_timezone
from app.outbound_payload import build_outbound_payload
from app.schemas import DetectionEvent, NotificationResult
from app.storage.event_store import EventStore


class EventNotifier:
    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self, event_store: EventStore | None = None) -> None:
        self.event_store = event_store or EventStore()
        self.tz, self.timezone_warning = resolve_timezone(settings.app_timezone)

    # 이 메서드는 감지 이벤트를 외부 서버로 전송하고 결과를 반환합니다.
    def send_event(self, event: DetectionEvent) -> NotificationResult:
        payload = build_outbound_payload(
            event,
            sent_at=datetime.now(self.tz),
            timezone_warning=self.timezone_warning,
        )
        if payload is None:
            return NotificationResult(success=True, attempts=0, detail="outbound 대상 이벤트 아님 - 전송 생략")

        if not settings.spring_boot_event_url:
            self.event_store.append_outbox(payload)
            return NotificationResult(success=True, attempts=1, detail="spring url 미설정 - outbox에 로컬 저장")

        attempts = 0
        last_error = ""
        while attempts < settings.retry_max_attempts:
            attempts += 1
            try:
                with httpx.Client(timeout=settings.http_timeout_seconds) as client:
                    response = client.post(settings.spring_boot_event_url, json=payload)
                    response.raise_for_status()
                return NotificationResult(success=True, attempts=attempts, detail="spring boot 전송 성공")
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = str(exc)
                time.sleep(settings.retry_backoff_seconds)

        self.event_store.append_outbox(payload | {"last_error": last_error})
        return NotificationResult(success=False, attempts=attempts, detail=last_error)

    # 이 메서드는 보호 대상자의 수면 시간 설정 정보를 조회합니다.
    def get_sleep_time_setting(self, resident_id: int) -> dict:
        if not settings.spring_boot_sleep_setting_url:
            return {"resident_id": resident_id, "sleep_time": None, "source": "local-default"}

        with httpx.Client(timeout=settings.http_timeout_seconds) as client:  # pragma: no cover - network dependent
            response = client.get(settings.spring_boot_sleep_setting_url, params={"residentId": resident_id})
            response.raise_for_status()
            return response.json()

    # 이 메서드는 실패한 전송 내역을 다시 전송합니다.
    def retry_send(self) -> dict:
        outbox = settings.outbox_jsonl
        if not outbox.exists():
            return {"retried": 0, "succeeded": 0, "failed": 0}

        lines = outbox.read_text(encoding="utf-8").splitlines()
        if not lines:
            return {"retried": 0, "succeeded": 0, "failed": 0}

        succeeded: list[dict] = []
        failed: list[dict] = []
        retried = 0

        for line in lines:
            retried += 1
            payload = json.loads(line)
            try:
                event = DetectionEvent.model_validate(payload)
                result = self.send_event(event)
                if result.success:
                    succeeded.append(payload)
                else:
                    failed.append(payload)
            except Exception:
                failed.append(payload)

        remaining_lines = [json.dumps(item, ensure_ascii=False) for item in failed]
        outbox.write_text("\n".join(remaining_lines) + ("\n" if remaining_lines else ""), encoding="utf-8")
        return {"retried": retried, "succeeded": len(succeeded), "failed": len(failed)}
