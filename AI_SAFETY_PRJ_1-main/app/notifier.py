from __future__ import annotations

import time
from datetime import datetime

import httpx

from app.core.config import settings
from app.core.timeutils import resolve_timezone
from app.outbound_payload import build_outbound_payload
from app.schemas import DetectionEvent, NotificationDisposition, NotificationResult
from app.storage.event_store import EventStore
from app.storage.outbox_store import OutboxRecord, OutboxStore


class EventNotifier:
    _last_attempt_at: str | None = None
    _last_success: bool | None = None
    _last_error: str | None = None

    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self, event_store: EventStore | None = None, outbox_store: OutboxStore | None = None) -> None:
        self.event_store = event_store or EventStore()
        self.outbox_store = outbox_store or OutboxStore()
        self.tz, self.timezone_warning = resolve_timezone(settings.app_timezone)

    # 이 메서드는 감지 이벤트를 외부 서버로 전송하고 결과를 반환합니다.
    def send_event(self, event: DetectionEvent) -> NotificationResult:
        payload = build_outbound_payload(
            event,
            sent_at=datetime.now(self.tz),
            timezone_warning=self.timezone_warning,
        )
        if payload is None:
            return NotificationResult(
                success=True,
                attempts=0,
                disposition=NotificationDisposition.SKIPPED,
                detail="outbound 대상 이벤트 아님 - 전송 생략",
            )

        if not self._is_delivery_enabled():
            self._queue_payload(payload, reason="url_missing")
            return NotificationResult(
                success=True,
                attempts=0,
                disposition=NotificationDisposition.QUEUED,
                detail="spring url 미설정/비활성 - outbox에 적재",
            )

        attempts = 0
        last_error = ""
        while attempts < settings.retry_max_attempts:
            attempts += 1
            ok, error_message = self._post_payload(payload)
            if ok:
                return NotificationResult(
                    success=True,
                    attempts=attempts,
                    disposition=NotificationDisposition.DELIVERED,
                    detail="spring boot 전송 성공",
                )
            last_error = error_message
            if attempts < settings.retry_max_attempts:
                time.sleep(settings.retry_backoff_seconds)

        self._queue_payload(payload, reason="delivery_failed", last_error=last_error)
        return NotificationResult(
            success=False,
            attempts=attempts,
            disposition=NotificationDisposition.FAILED_QUEUED,
            detail=last_error,
        )

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
        records = self.outbox_store.read_records()
        if not records:
            return {"retried": 0, "succeeded": 0, "failed": 0}

        retried = 0
        succeeded = 0
        remaining: list[OutboxRecord] = []

        for record in records:
            retried += 1
            if not isinstance(record, OutboxRecord):
                remaining.append(
                    OutboxRecord(
                        payload={"invalid_record": record},
                        source="retry",
                        reason="retry_record_invalid",
                        last_error="outbox record parse failure",
                    )
                )
                continue

            if not self._is_delivery_enabled():
                remaining.append(record)
                continue

            ok, error_message = self._post_with_retries(record.payload)
            if ok:
                succeeded += 1
                continue

            remaining.append(
                OutboxRecord(
                    payload=record.payload,
                    queued_at=record.queued_at,
                    source="retry",
                    reason="delivery_failed",
                    last_error=error_message,
                )
            )

        self.outbox_store.overwrite(remaining)
        return {"retried": retried, "succeeded": succeeded, "failed": len(remaining)}

    def _is_delivery_enabled(self) -> bool:
        return settings.spring_boot_delivery_enabled and bool(settings.spring_boot_event_url)

    def _post_with_retries(self, payload: dict[str, object]) -> tuple[bool, str]:
        attempts = 0
        last_error = ""
        while attempts < settings.retry_max_attempts:
            attempts += 1
            ok, error_message = self._post_payload(payload)
            if ok:
                return True, ""
            last_error = error_message
            if attempts < settings.retry_max_attempts:
                time.sleep(settings.retry_backoff_seconds)
        return False, last_error

    def _post_payload(self, payload: dict[str, object]) -> tuple[bool, str]:
        try:
            EventNotifier._last_attempt_at = datetime.now().isoformat()
            with httpx.Client(timeout=settings.http_timeout_seconds) as client:
                response = client.post(settings.spring_boot_event_url, json=payload)
                response.raise_for_status()
            EventNotifier._last_success = True
            EventNotifier._last_error = None
            return True, ""
        except Exception as exc:  # pragma: no cover - network dependent
            EventNotifier._last_success = False
            EventNotifier._last_error = str(exc)
            return False, str(exc)

    def _queue_payload(
        self,
        payload: dict[str, object],
        *,
        reason: str,
        last_error: str | None = None,
    ) -> OutboxRecord:
        return self.outbox_store.enqueue(payload, reason=reason, last_error=last_error)

    def diagnostics(self) -> dict[str, object]:
        return {
            "delivery_enabled": self._is_delivery_enabled(),
            "event_url": settings.spring_boot_event_url,
            "last_attempt_at": EventNotifier._last_attempt_at,
            "last_success": EventNotifier._last_success,
            "last_error": EventNotifier._last_error,
            "outbox_pending_count": self.outbox_store.count(),
        }
