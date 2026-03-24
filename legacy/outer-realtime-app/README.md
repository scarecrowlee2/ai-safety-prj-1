# Legacy Outer Realtime App (Documentation Stub Only)

This directory is no longer a runnable application.

## Status

- **Legacy/reference-only**
- **Not the primary app**
- Preserved only for migration history and rollback notes

## Active application

Use the inner project only:

- `AI_SAFETY_PRJ_1-main/`
- Entrypoint: `AI_SAFETY_PRJ_1-main/app/main.py`
- Run command (from `AI_SAFETY_PRJ_1-main/`):

```bash
uvicorn app.main:app --reload
```

## What changed in final cleanup

Legacy runnable duplicate code was moved out of this directory into:

- `legacy/archived_realtime_reference/outer-realtime-app/`

Within that archive, duplicate `core/`, `detectors/`, and `storage/` modules were removed after confirming the inner app has active equivalents.

## Legacy docs retained here

- `REALTIME_DETECTION_GUIDE.md`
- `STREAMING_GUIDE.md`

These describe the former outer prototype flow and are retained as historical notes.
