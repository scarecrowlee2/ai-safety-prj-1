from __future__ import annotations

from datetime import timezone

from app.core.timeutils import UTC_FALLBACK_NOTE, resolve_timezone


# 이 테스트는 잘못된 타임존 입력 시 UTC로 안전하게 대체되는지 검증합니다.
def test_resolve_timezone_falls_back_to_utc_for_unknown_zone() -> None:
    tz, warning = resolve_timezone("Definitely/Unknown_Timezone")
    assert tz is timezone.utc
    assert warning == UTC_FALLBACK_NOTE
