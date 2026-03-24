# Realtime Detection Guide (현재 코드 기준)

`AI_SAFETY_PRJ_1-main/`의 공식 realtime 사용 요약입니다.

## 1) 실행 기준

- 공식 엔트리포인트: `app.main:app`
- 실행 명령:

```bash
uvicorn app.main:app --reload
```

> `uvicorn app.api.stream:app` 는 현재 공식 실행 경로가 아닙니다.

## 2) 공식 realtime 경로와 역할

- `GET /realtime`  
  운영 대시보드 UI
- `GET /realtime/video`  
  대시보드가 사용하는 MJPEG 영상 스트림(점검 시 직접 호출 가능)
- `GET /api/v1/realtime/events`  
  최근 실시간 이벤트 목록(JSON)
- `GET /api/v1/realtime/status`  
  최근 이벤트 기반 상태 요약(JSON)

## 3) 업로드 분석 API와 범위 차이

- 업로드 분석 엔드포인트: `POST /api/v1/analyze/video`
- 업로드 분석 detector 범위: `fall`, `inactive`
- `violence`는 현재 realtime 전용 detector입니다.

즉, realtime detector 범위(`fall/inactive/violence`)와 upload analyzer 범위(`fall/inactive`)는 다릅니다.

## 4) Inactive 운영 주의사항

- 운영에서는 `ENABLE_YOLO_PERSON_GATE=true` 권장을 기본으로 봅니다.
- gate 비활성 시 inactive detector가 `degraded`(제한 모드) 상태가 될 수 있습니다.
- 상태 확인: `GET /api/v1/health`의 `detectors.inactive.mode`, `person_gate_enabled`, `person_gate_ready`

## 5) 최소 점검 체크리스트

1. `/realtime` 로 대시보드 렌더링 확인
2. `/realtime/video` 가 `multipart/x-mixed-replace`로 응답하는지 확인
3. `/api/v1/realtime/events` JSON 확인
4. `/api/v1/realtime/status` JSON 확인
5. `/api/v1/health`에서 detector 상태/경고 확인
