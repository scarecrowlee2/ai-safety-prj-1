from __future__ import annotations

from datetime import timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC_FALLBACK_NOTE = "configured timezone unavailable - falling back to UTC"


# 이 함수는 타임존 문자열을 해석하고 실패 시 기본 타임존으로 대체합니다.
def resolve_timezone(timezone_key: str) -> tuple[tzinfo, str | None]:
    try:
        return ZoneInfo(timezone_key), None
    except ZoneInfoNotFoundError:
        return timezone.utc, UTC_FALLBACK_NOTE
