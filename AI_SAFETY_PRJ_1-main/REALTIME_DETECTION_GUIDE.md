# Realtime Detection Guide (Inner Official App)

이 문서는 `AI_SAFETY_PRJ_1-main/` 기준 realtime 기능 사용 가이드입니다.

## 공식 실행 기준

- 공식 루트: `AI_SAFETY_PRJ_1-main/`
- 공식 엔트리포인트: `app.main:app`
- 실행:

```bash
uvicorn app.main:app --reload
```

> `uvicorn app.api.stream:app` 는 현재 공식 실행 경로가 아닙니다.

## Realtime 접근 경로

- 대시보드: `GET /realtime`
- 비디오 스트림(MJPEG): `GET /realtime/video`
- 최근 이벤트 API: `GET /api/v1/realtime/events`

## 로그/저장 위치

- 실시간 이벤트 로그(JSONL): `data/realtime_events.jsonl`
- 업로드 분석/공통 이벤트 저장: `data/events.db`
- 실패 전송 outbox: `data/outbox/events.jsonl`

## 운영 확인 포인트

1. `/realtime` 페이지가 로드되는지 확인
2. `/realtime/video` 응답이 `multipart/x-mixed-replace` 인지 확인
3. `/api/v1/realtime/events` 응답이 JSON인지 확인
4. 웹캠 미연결 환경에서는 스트림에서 fallback 상태 프레임이 나오는지 확인

보다 넓은 개발/환경설정/업로드 API 내용은 `README.md`를 기준으로 확인하세요.
