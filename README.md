# Repository Execution Guide

## Official application (single source of truth)

Use the inner project only:

- **Official root:** `AI_SAFETY_PRJ_1-main/`
- **Official FastAPI entrypoint:** `app.main:app`
- **Run command (from `AI_SAFETY_PRJ_1-main/`):**

```bash
uvicorn app.main:app --reload
```

## Primary validation routes

After startup, use these routes for smoke checks:

- `GET /api/v1/health`
- `GET /realtime`
- `GET /realtime/video`
- `GET /api/v1/realtime/events`
- `POST /api/v1/analyze/video`
- `POST /api/v1/retry-outbox`

For full setup/run/verification details, see:

- `AI_SAFETY_PRJ_1-main/README.md`

## Legacy status

The outer/legacy app paths are **not** official execution paths:

- `legacy/outer-realtime-app/` (documentation stub only)
- `legacy/archived_realtime_reference/` (archive/reference only)

If any legacy note conflicts with active instructions, always follow `AI_SAFETY_PRJ_1-main/README.md`.
