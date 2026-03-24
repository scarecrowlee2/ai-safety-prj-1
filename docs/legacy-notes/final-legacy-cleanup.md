# Final Legacy Cleanup Notes

Date: 2026-03-24

## Official active app

- Active runtime/development app: `AI_SAFETY_PRJ_1-main/`
- Active FastAPI entrypoint: `AI_SAFETY_PRJ_1-main/app/main.py`

## Legacy evaluation summary

### Fully superseded by inner project (safe to remove from legacy runnable layout)

- Legacy duplicate detector modules (`fall`, `inactive`, `violence`)
- Legacy duplicate helper/storage modules (`core/video`, `storage/event_logger`)
- Legacy package scaffolding and compiled cache artifacts (`__init__.py`, `__pycache__`, `*.pyc`)

Reason: equivalent realtime, detector, storage, and route flows are already present and wired in the inner app under `AI_SAFETY_PRJ_1-main/app/`.

### Preserved as archive/reference

- Legacy realtime route composition snapshot (`app/api/stream.py`)
- Legacy realtime dashboard template/static assets
- Legacy migration guides (`REALTIME_DETECTION_GUIDE.md`, `STREAMING_GUIDE.md`)

Reason: useful for rollback/context and UI history without keeping a second active app path.

### Risky/uncertain items intentionally not deleted

- Legacy operational guides are retained as historical references until final end-to-end signoff.

## Structural intent after cleanup

- `legacy/outer-realtime-app/` is now documentation-stub only (non-runnable).
- `legacy/archived_realtime_reference/` contains curated archival reference artifacts.
- New feature development must occur only in `AI_SAFETY_PRJ_1-main/`.
