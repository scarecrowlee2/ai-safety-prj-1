from __future__ import annotations

from app.core.realtime_notifier_policy import RealtimeNotifierIntegration
from app.notifier import EventNotifier
from app.storage.event_store import EventStore

realtime_notifier = RealtimeNotifierIntegration(notifier=EventNotifier(EventStore()))


def dispatch_realtime_logged_events(*, logged_events: list[dict], frame=None) -> list[dict]:
    return realtime_notifier.notify_logged_events(logged_events, frame=frame)
