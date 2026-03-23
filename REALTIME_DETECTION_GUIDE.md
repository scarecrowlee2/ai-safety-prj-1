# REALTIME DETECTION GUIDE

## 이번 버전에서 추가된 것

### 1) 더 선명한 화면 경고
- 낙상/기절: 주시 상태는 노랑, 실제 경고는 빨강
- 무응답: 주시 상태는 하늘색 계열, 실제 경고는 주황
- 폭행 의심: 주시 상태는 보라, 실제 경고는 진한 자홍

화면 상단 상태 패널과 각 사람 박스 색을 다르게 표시해서 어떤 이벤트가 걸렸는지 바로 보이게 했습니다.

### 2) 이벤트 로그 저장
- 로그 파일 경로: `data/realtime_events.jsonl`
- 형식: JSON Lines
- 새 경고가 처음 발생하는 순간만 1줄씩 기록

예시:
```json
{"logged_at":"2026-03-23T01:23:45.000000+00:00","event_type":"fall","message":"낙상/기절 의심 이벤트가 새로 감지되었습니다.","stream_timestamp_sec":12.34,"payload":{"is_candidate":true,"should_alert":true}}
```

## 실행

```bash
pip install fastapi uvicorn opencv-python numpy
uvicorn app.api.stream:app --reload
```

브라우저:
```text
http://127.0.0.1:8000/
```

## 로그 확인

스트리밍을 켠 뒤 감지가 발생하면 아래 파일이 생깁니다.

```text
data/realtime_events.jsonl
```

파일을 메모장이나 VSCode로 열면 감지 시점별 기록을 확인할 수 있습니다.
