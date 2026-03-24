# Archived Realtime Reference (Non-Primary, Non-Runnable)

This folder preserves selected artifacts from the former outer realtime prototype for historical/UI reference.

## Scope of preserved artifacts

- `outer-realtime-app/app/api/stream.py` (legacy realtime route composition reference)
- `outer-realtime-app/app/templates/realtime_monitor.html` (legacy dashboard template)
- `outer-realtime-app/app/static/css/realtime_monitor.css` (legacy styling)
- `outer-realtime-app/app/static/js/realtime_monitor.js` (legacy dashboard JS)

## Cleanup notes

The following duplicate legacy modules were intentionally removed from this archive during final consolidation because equivalent active implementations already exist in `AI_SAFETY_PRJ_1-main/app/`:

- `core/`
- `detectors/`
- `storage/`
- package `__init__.py` files and compiled `__pycache__` artifacts

For active development and runtime, use only `AI_SAFETY_PRJ_1-main/`.
