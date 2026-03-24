# Repository Execution Guide

## Official main application root

The **official FastAPI application** is the inner project at:

- `AI_SAFETY_PRJ_1-main/`

Use this directory as the primary working root for development, testing, and runtime.

## Official entrypoint

From `AI_SAFETY_PRJ_1-main/`, run:

```bash
uvicorn app.main:app --reload
```

Primary routes served by the official app include:

- `/realtime`
- `/realtime/video`
- `/api/v1/realtime/events`
- upload-analysis routes under `/api/v1/analyze/*`

## Legacy material status

Legacy outer realtime artifacts were finalized into documentation + archive form:

- Docs stub: `legacy/outer-realtime-app/`
- Archived reference code/assets: `legacy/archived_realtime_reference/`

The archived reference area is **not** a runnable app and exists only for historical/UI rollback reference.

## Developer note

If commands/docs conflict, prefer the inner app docs at:

- `AI_SAFETY_PRJ_1-main/README.md`
