# Repository Execution Guide

## Official main application root

The **official FastAPI application** is now the inner project at:

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

## Legacy outer realtime app status

The previous outer realtime app has been intentionally isolated under:

- `legacy/outer-realtime-app/`

This outer app is now **legacy/reference-only** and is **not** the primary execution path.
Do not use it as the default runtime unless you are explicitly doing rollback/reference work.

## Developer note

If commands/docs conflict, prefer the inner app docs at:

- `AI_SAFETY_PRJ_1-main/README.md`
