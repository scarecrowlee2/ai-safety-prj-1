from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings


class OutboxRecord(BaseModel):
    """JSONL record stored for deferred outbound delivery."""

    payload: dict[str, object]
    queued_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: Literal["notify", "retry"] = "notify"
    reason: Literal["url_missing", "delivery_failed", "retry_record_invalid"]
    last_error: str | None = None


class OutboxStore:
    def __init__(self, outbox_path: Path | None = None) -> None:
        self.path = Path(outbox_path or settings.outbox_jsonl)

    def enqueue(
        self,
        payload: dict[str, object],
        *,
        reason: Literal["url_missing", "delivery_failed", "retry_record_invalid"],
        last_error: str | None = None,
        source: Literal["notify", "retry"] = "notify",
    ) -> OutboxRecord:
        record = OutboxRecord(payload=payload, reason=reason, last_error=last_error, source=source)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return record

    def read_records(self) -> list[OutboxRecord | dict[str, object]]:
        if not self.path.exists():
            return []

        raw_lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[OutboxRecord | dict[str, object]] = []
        for line in raw_lines:
            if not line.strip():
                continue
            try:
                decoded = json.loads(line)
            except json.JSONDecodeError:
                records.append({"_raw_line": line, "_decode_error": "json_decode_error"})
                continue

            try:
                records.append(OutboxRecord.model_validate(decoded))
            except ValidationError:
                # Backward compatibility: old outbox format was raw payload JSON.
                if isinstance(decoded, dict) and "payload" not in decoded:
                    records.append(
                        OutboxRecord(
                            payload=decoded,
                            reason="delivery_failed",
                            source="retry",
                            last_error="legacy_outbox_record_format",
                        )
                    )
                else:
                    records.append(decoded if isinstance(decoded, dict) else {"_invalid": True})
        return records

    def overwrite(self, records: list[OutboxRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not records:
            self.path.write_text("", encoding="utf-8")
            return

        text = "\n".join(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) for record in records) + "\n"
        self.path.write_text(text, encoding="utf-8")
