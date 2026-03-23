
# 실시간 웹캠 + 낙상 감지 + 스트리밍 구조 설명

## 전체 흐름

웹캠 → 프레임 읽기 → AI 분석 → FastAPI 스트리밍 → 웹 브라우저

---

## 1. WebcamReader (video.py)

- OpenCV로 웹캠 연결
- frame을 generator 형태로 반환

```
for frame in reader.read():
```

---

## 2. 분석 단계

현재는 placeholder:

```
cv2.putText(img, "Analyzing...")
```

👉 여기에 낙상 감지 모델 연결하면 됨

---

## 3. FastAPI 스트리밍 (stream.py)

### 핵심
- `/video` endpoint
- StreamingResponse 사용

### 흐름

1. 프레임 읽음
2. JPEG 인코딩
3. multipart 형식으로 전송

---

## 4. 실행 방법

```
pip install fastapi uvicorn opencv-python
uvicorn app.api.stream:app --reload
```

브라우저:
```
http://localhost:8000/video
```

---

## 핵심 포인트

- generator 기반 → 실시간 처리
- FastAPI → HTTP 스트리밍
- 모델만 연결하면 바로 서비스 가능
