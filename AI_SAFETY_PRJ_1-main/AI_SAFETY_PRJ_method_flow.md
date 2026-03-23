# AI 스마트 생활안전 서비스 MVP - 메서드 흐름 정리

## 문서 목적

이 문서는 업로드된 Python 프로그램의 **실행 흐름**을 메서드 단위로 정리한 것이다.  
각 메서드마다 아래 관점으로 설명한다.

- **입력값**: 어떤 값을 받는지
- **처리 흐름**: 내부에서 무엇을 하는지
- **반환값**: 무엇을 돌려주는지
- **부수효과**: 파일 저장, DB 기록, HTTP 호출 같은 외부 영향

---

## 전체 실행 흐름 요약

### 1. API로 영상 분석 요청이 들어오는 경우

1. `POST /api/v1/analyze/video` 호출
2. 업로드된 비디오를 임시 폴더에 저장
3. `VideoAnalyzer.analyze_video()` 호출
4. `VideoReader.read()` 로 비디오를 프레임 단위로 샘플링
5. 각 프레임마다 `VideoAnalyzer._process_frame()` 수행
6. 내부에서
   - `FallDetector` 로 낙상 후보 판단
   - `InactiveDetector` 로 장시간 무동작 판단
   - 필요 시 스냅샷 저장
   - 이벤트 DB 저장
   - 메트릭 로그 저장
7. 최종적으로 `AnalyzeVideoResponse` 형태의 결과 반환
8. `notify=true` 이면 `EventNotifier.send_event()` 로 Spring Boot 전송 시도

### 2. CLI로 분석하는 경우

1. `python -m app.cli --resident-id ... --video ...`
2. `main()` 에서 인자 파싱
3. `VideoAnalyzer.analyze_video()` 수행
4. 선택적으로 `EventNotifier.send_event()` 수행
5. JSON 문자열을 표준 출력으로 출력

---

## 데이터 모델 요약

아래 클래스들은 "메서드"보다 **입출력 구조** 역할이 크다.

- `EventType`: `FALL`, `INACTIVE`, `VIOLENCE`
- `EventStatus`: `PENDING`, `CONFIRMED`, `CLOSED`
- `EventMetrics`: 감지 관련 수치
- `DetectionEvent`: 하나의 감지 이벤트
- `AnalyzeVideoResponse`: 영상 분석 응답 전체
- `NotificationResult`: 외부 전송 결과
- `CaptureRecord`: 저장된 스냅샷 정보
- `FeatureFrame`: 프레임 특징값 묶음

---

# 1. 진입점 / API

## app/main.py

### `root() -> dict`

**입력값**
- 없음

**처리 흐름**
1. 루트 경로(`/`) 접근 시 고정 안내 정보를 만든다.
2. 서비스 메시지, Swagger 문서 경로, 헬스체크 경로를 담는다.

**반환값**
- `dict`
  - `message`
  - `docs`
  - `health`

**부수효과**
- 없음

---

## app/api/routes.py

### `health() -> dict`

**입력값**
- 없음

**처리 흐름**
1. `VideoAnalyzer()` 인스턴스를 생성한다.
2. `analyzer.diagnostics()` 를 호출한다.
3. 앱 상태, 환경값, 감지기 상태, 경고 목록을 합쳐 응답 딕셔너리를 만든다.

**반환값**
- 상태 정보가 담긴 `dict`

**부수효과**
- 내부적으로 감지기 초기화가 발생할 수 있음

---

### `analyze_video(resident_id: int, video: UploadFile, notify: bool=False) -> dict`

**입력값**
- `resident_id`: 보호 대상자 ID
- `video`: 업로드된 비디오 파일
- `notify`: 분석 후 외부 전송 여부

**처리 흐름**
1. 업로드 파일명에서 확장자를 뽑는다.
2. `settings.temp_upload_dir` 아래 임시 저장 경로를 만든다.
3. `await video.read()` 로 업로드 내용을 전부 읽는다.
4. 읽은 바이트를 임시 파일로 저장한다.
5. `VideoAnalyzer()` 를 생성한다.
6. `analyzer.analyze_video(resident_id, upload_path)` 를 호출한다.
7. `notify` 가 `True` 이면
   1. `EventNotifier(EventStore())` 생성
   2. 분석 결과의 각 이벤트에 대해 `notifier.send_event(event)` 호출
   3. 알림 결과를 `notification_results` 로 응답에 추가
8. `notify` 가 `False` 이면 분석 결과만 JSON으로 반환한다.
9. 처리 중 예외가 나면 `HTTPException(400)` 으로 감싼다.

**반환값**
- 분석 결과 `dict`
- `notify=True` 이면 `notification_results` 포함

**부수효과**
- 업로드 비디오 파일 저장
- 이벤트 발생 시 스냅샷 저장
- SQLite 저장 가능
- outbox 파일 저장 가능
- 외부 HTTP 전송 가능

---

### `retry_outbox() -> dict`

**입력값**
- 없음

**처리 흐름**
1. `EventNotifier(EventStore())` 생성
2. `notifier.retry_send()` 호출
3. 저장된 outbox 이벤트들의 재전송 결과를 반환

**반환값**
- `dict`
  - `retried`
  - `succeeded`
  - `failed`

**부수효과**
- outbox 파일을 다시 읽고 덮어씀
- 외부 HTTP 재전송 가능

---

# 2. CLI

## app/cli.py

### `build_parser() -> argparse.ArgumentParser`

**입력값**
- 없음

**처리 흐름**
1. `ArgumentParser` 생성
2. `--resident-id`, `--video`, `--notify` 옵션 등록
3. 파서 객체 반환

**반환값**
- `argparse.ArgumentParser`

**부수효과**
- 없음

---

### `main() -> None`

**입력값**
- 직접 인자를 받지 않음
- 실제로는 커맨드라인 인자를 `parse_args()` 로 읽음

**처리 흐름**
1. `build_parser()` 호출
2. CLI 인자를 파싱한다.
3. `VideoAnalyzer()` 생성
4. `analyze_video(resident_id, video_path)` 호출
5. 결과를 `model_dump(mode="json")` 로 직렬화한다.
6. `--notify` 가 켜져 있으면
   1. `EventNotifier(EventStore())` 생성
   2. 각 이벤트를 `send_event()` 로 전송
   3. 전송 결과를 payload에 추가
7. 최종 payload를 JSON 문자열로 출력한다.

**반환값**
- 명시적 반환 없음 (`None`)

**부수효과**
- 표준 출력에 JSON 출력
- 파일 저장/DB 저장/외부 전송 가능

---

# 3. 분석 오케스트레이션

## app/core/analyzer.py

## `VideoAnalyzer.__init__(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. `resolve_timezone(settings.app_timezone)` 로 타임존 결정
2. `FallDetector()` 생성
3. `InactiveDetector()` 생성
4. `SnapshotStorage()` 생성
5. `EventStore()` 생성
6. `MetricsLogger()` 생성
7. 이벤트별 마지막 발행 시각을 저장할 `_last_emitted_at` 딕셔너리 초기화

**반환값**
- 없음

**부수효과**
- 감지기/저장소 초기화
- 내부적으로 디렉터리/DB 준비가 이미 끝난 상태를 사용

---

### `diagnostics(self) -> dict`

**입력값**
- 없음

**처리 흐름**
1. `_build_warnings()` 호출
2. 타임존, 경고 목록, 감지기 상태를 조합
3. 낙상 감지기는 `fall_detector.status()` 결과 사용
4. 무응답 감지기는 현재 코드상 고정 상태 정보 사용

**반환값**
- 진단용 상태 `dict`

**부수효과**
- 없음

---

### `analyze_video(self, resident_id: int, video_path: str | Path) -> AnalyzeVideoResponse`

**입력값**
- `resident_id`: 보호 대상자 ID
- `video_path`: 비디오 파일 경로

**처리 흐름**
1. `VideoReader(video_path, settings.sample_fps)` 생성
2. `reader.read()` 호출
   - 비디오 메타데이터
   - 샘플링된 프레임 제너레이터
   를 받음
3. 빈 이벤트 리스트 생성
4. 프레임을 하나씩 순회하면서 `_process_frame()` 호출
5. 각 프레임에서 나온 이벤트들을 누적
6. 모든 프레임 처리가 끝나면 `AnalyzeVideoResponse` 생성
   - `resident_id`
   - `video_name`
   - `events`
   - `warnings`

**반환값**
- `AnalyzeVideoResponse`

**부수효과**
- 각 프레임 처리 과정에서 로그 저장/스냅샷 저장/DB 저장 가능

---

### `_build_warnings(self) -> list[str]`

**입력값**
- 없음

**처리 흐름**
1. 빈 경고 리스트 생성
2. 타임존 fallback 경고가 있으면 추가
3. 낙상 감지기가 비활성화되었고 이유가 있으면 경고 추가
4. 경고 리스트 반환

**반환값**
- 경고 문자열 리스트

**부수효과**
- 없음

---

### `_process_frame(self, resident_id: int, frame_image, timestamp_sec: float) -> list[DetectionEvent]`

**입력값**
- `resident_id`: 보호 대상자 ID
- `frame_image`: 현재 프레임 이미지 (`numpy.ndarray`)
- `timestamp_sec`: 영상 내 프레임 시각(초)

**처리 흐름**
1. 현재 시각 `detected_at` 생성
2. `timestamp_sec` 를 ms 단위로 바꿔 `timestamp_ms` 생성

#### A. 낙상 감지 흐름
3. `fall_detector.extract_keypoints(frame_image, timestamp_ms)` 호출
4. `fall_detector.is_fallen(keypoints)` 로 낙상 후보 여부 판단
5. `fall_detector.check_duration(timestamp_sec, fall_decision)` 로 자세 지속 시간 반영
6. 낙상 관련 메트릭을 `metrics_logger.append(..., stream_name="fall", ...)` 로 JSONL 로그 저장
7. 아래 조건을 모두 만족하면 FALL 이벤트 발행
   - `fall_detector.should_emit(fall_decision)` 가 `True`
   - `_can_emit(EventType.FALL, timestamp_sec)` 가 `True`
8. FALL 이벤트 발행 시
   1. `snapshot_storage.save(...)` 로 스냅샷 저장
   2. `DetectionEvent` 생성
   3. `event_store.save_event(event, capture_record)` 로 DB 저장
   4. emitted 리스트에 추가
   5. `_mark_emitted(...)` 로 쿨다운 기준 시각 기록
   6. `fall_detector.horizontal_streak_seconds = 0.0` 으로 streak 초기화

#### B. 장시간 무응답 감지 흐름
9. `inactive_detector.evaluate(frame_image, timestamp_sec)` 호출
10. 무응답 관련 메트릭을 `metrics_logger.append(..., stream_name="inactive", ...)` 로 저장
11. 아래 조건을 모두 만족하면 INACTIVE 이벤트 발행
   - `inactive_detector.should_emit(inactive_decision)` 가 `True`
   - `_can_emit(EventType.INACTIVE, timestamp_sec)` 가 `True`
12. INACTIVE 이벤트 발행 시
   1. 스냅샷 저장
   2. `DetectionEvent` 생성
   3. DB 저장
   4. emitted 리스트에 추가
   5. `_mark_emitted(...)` 호출
   6. `inactive_detector.no_motion_seconds = 0.0` 으로 누적 시간 초기화

13. 프레임에서 발생한 이벤트 리스트 반환

**반환값**
- `list[DetectionEvent]`

**부수효과**
- 메트릭 로그 파일 기록
- 스냅샷 이미지 파일 저장
- SQLite 이벤트 저장

---

### `_can_emit(self, event_type: EventType, timestamp_sec: float) -> bool`

**입력값**
- `event_type`: 이벤트 종류
- `timestamp_sec`: 현재 프레임 시각

**처리 흐름**
1. `_last_emitted_at` 에서 해당 이벤트 타입의 마지막 발생 시각을 조회
2. 이전 기록이 없으면 바로 `True`
3. 이전 기록이 있으면 현재 시각과 차이를 계산
4. `settings.no_event_cooldown_seconds` 이상 지났는지 판단

**반환값**
- 발행 가능 여부 `bool`

**부수효과**
- 없음

---

### `_mark_emitted(self, event_type: EventType, timestamp_sec: float) -> None`

**입력값**
- `event_type`: 이벤트 종류
- `timestamp_sec`: 현재 프레임 시각

**처리 흐름**
1. `_last_emitted_at[event_type] = timestamp_sec` 저장

**반환값**
- 없음

**부수효과**
- 내부 상태 변경

---

# 4. 설정 / 유틸

## app/core/config.py

### `Settings.ensure_directories(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. 데이터 디렉터리 생성
2. 모델 디렉터리 생성
3. 스냅샷 디렉터리 생성
4. 업로드 임시 디렉터리 생성
5. outbox 파일의 부모 디렉터리 생성
6. SQLite DB 파일의 부모 디렉터리 생성

**반환값**
- 없음

**부수효과**
- 디렉터리 생성

---

## app/core/timeutils.py

### `resolve_timezone(timezone_key: str) -> tuple[tzinfo, str | None]`

**입력값**
- `timezone_key`: 예: `"Asia/Seoul"`

**처리 흐름**
1. `ZoneInfo(timezone_key)` 로 타임존 객체 생성 시도
2. 성공 시 `(타임존 객체, None)` 반환
3. 실패 시 `timezone.utc` 와 fallback 경고 문자열 반환

**반환값**
- `(tzinfo, warning_or_none)`

**부수효과**
- 없음

---

## app/core/video.py

### `VideoReader.__init__(self, video_path: str | Path, sample_fps: float) -> None`

**입력값**
- `video_path`: 비디오 파일 경로
- `sample_fps`: 몇 FPS로 샘플링할지

**처리 흐름**
1. 경로를 문자열로 저장
2. 샘플링 FPS를 저장

**반환값**
- 없음

**부수효과**
- 없음

---

### `VideoReader.read(self) -> tuple[VideoMetadata, Generator[VideoFrame, None, None]]`

**입력값**
- 없음
- 생성자에서 받은 `video_path`, `sample_fps` 사용

**처리 흐름**
1. `cv2.VideoCapture` 로 비디오를 연다.
2. 열리지 않으면 `ValueError` 발생
3. 원본 FPS, 해상도, 총 프레임 수를 읽는다.
4. 총 길이(`duration_sec`) 계산
5. `VideoMetadata` 생성
6. 샘플링 stride 계산
   - 예: 원본 30fps, sample_fps=5 이면 대략 6프레임마다 1개 추출
7. 내부 제너레이터를 정의한다.
8. 제너레이터 내부에서
   1. 프레임을 계속 읽음
   2. 끝나면 종료
   3. stride 에 맞는 프레임만 `VideoFrame` 으로 yield
   4. `finally` 에서 `capture.release()` 수행
9. `(metadata, generator())` 반환

**반환값**
- `VideoMetadata`
- `Generator[VideoFrame, None, None]`

**부수효과**
- 비디오 파일 열기/해제

---

# 5. 낙상 감지기

## app/detectors/fall.py

### `FallDetector.__init__(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. `landmarker` 를 `None` 으로 초기화
2. `enabled = False`
3. `disabled_reason = ""`
4. 수평 자세 누적 시간 `horizontal_streak_seconds = 0.0`
5. 이전 타임스탬프 초기화
6. `load_model()` 호출로 모델 로딩 시도

**반환값**
- 없음

**부수효과**
- 모델 로딩 시도

---

### `load_model(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. `close()` 호출로 기존 landmarker 정리
2. 설정에서 낙상 감지가 꺼져 있으면 `_disable(...)` 후 종료
3. `mediapipe` 패키지가 없으면 `_disable(...)`
4. `mp.tasks.vision` API 가 없으면 `_disable(...)`
5. 설정된 `.task` 모델 파일이 없으면 `_disable(...)`
6. 위 조건을 통과하면
   1. `BaseOptions(model_asset_path=...)` 생성
   2. `PoseLandmarkerOptions` 생성
   3. `PoseLandmarker.create_from_options()` 호출
   4. 성공 시 `enabled = True`
7. 초기화 중 예외가 나면 `_disable(...)`

**반환값**
- 없음

**부수효과**
- MediaPipe 모델 로딩
- 내부 상태 변경

---

### `_disable(self, reason: str) -> None`

**입력값**
- `reason`: 비활성화 이유 문자열

**처리 흐름**
1. `enabled = False`
2. `disabled_reason = reason`
3. `landmarker = None`

**반환값**
- 없음

**부수효과**
- 내부 상태 변경

---

### `close(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. `landmarker` 가 있고 `close()` 메서드가 있으면 닫음
2. `landmarker = None`

**반환값**
- 없음

**부수효과**
- 모델 리소스 해제

---

### `status(self) -> dict[str, Any]`

**입력값**
- 없음

**처리 흐름**
1. 감지기 활성화 여부
2. 백엔드 이름
3. 모델 경로
4. 비활성화 이유
를 딕셔너리로 묶음

**반환값**
- 상태 정보 `dict`

**부수효과**
- 없음

---

### `extract_keypoints(self, frame: np.ndarray, timestamp_ms: int) -> dict[str, Any] | None`

**입력값**
- `frame`: BGR 프레임 이미지
- `timestamp_ms`: 영상 타임스탬프(ms)

**처리 흐름**
1. 모델이 없거나 `mediapipe` 가 없으면 `None` 반환
2. BGR 프레임을 RGB 로 변환
3. `mp.Image` 생성
4. `landmarker.detect_for_video(mp_image, timestamp_ms)` 실행
5. `pose_landmarks` 가 없으면 `None` 반환
6. 이미지 가로/세로 크기 계산
7. 첫 번째 사람의 랜드마크를 사용
8. 각 랜드마크에 대해
   - 픽셀 좌표 `(x, y, z)` 계산
   - `visibility`, `presence` 기반 confidence 계산
9. 평균 visibility 계산
10. 랜드마크 원본, 좌표 맵, 평균 visibility, 이미지 크기를 딕셔너리로 반환

**반환값**
- 키포인트 정보 `dict`
- 또는 감지 실패 시 `None`

**부수효과**
- 모델 추론 수행

---

### `_landmark_point(self, landmarks: list[Any], index: int, image_w: int, image_h: int) -> tuple[float, float, float, float]`

**입력값**
- `landmarks`: MediaPipe 랜드마크 리스트
- `index`: 필요한 랜드마크 인덱스
- `image_w`, `image_h`: 이미지 크기

**처리 흐름**
1. 지정 인덱스 랜드마크를 꺼냄
2. 정규화 좌표를 픽셀 좌표로 변환
3. `visibility`, `presence` 중 작은 값을 confidence 로 계산
4. `(x, y, z, confidence)` 반환

**반환값**
- `(x, y, z, confidence)` 튜플

**부수효과**
- 없음

---

### `is_fallen(self, keypoints: dict[str, Any] | None) -> FallDecision`

**입력값**
- `keypoints`: `extract_keypoints()` 결과 또는 `None`

**처리 흐름**
1. 키포인트가 없으면 `FallDecision(False, 0.0, None, None)` 반환
2. 평균 포즈 신뢰도(`pose_confidence`) 확인
3. 최소 visibility 보다 낮으면 낙상 아님으로 반환
4. 어깨/엉덩이 랜드마크를 꺼냄
5. 어깨 중심점, 엉덩이 중심점 계산
6. 몸통 벡터의 세로축 기준 기울기 각도 계산
   - `torso_angle_from_vertical_deg`
7. 신뢰도 높은 랜드마크들만 사용해 bounding box 폭/높이 계산
8. `bbox_aspect_ratio` 계산
9. 낙상 후보 조건 판정
   - 기본: 몸통 각도 >= 임계값
   - 추가 보정: bbox 가 가로로 넓으면 각도 기준을 조금 완화
10. `FallDecision` 반환

**반환값**
- `FallDecision`
  - `is_candidate`
  - `pose_confidence`
  - `torso_angle_from_vertical_deg`
  - `bbox_aspect_ratio`
  - `horizontal_seconds`(초기값)

**부수효과**
- 없음

---

### `check_duration(self, timestamp_sec: float, decision: FallDecision) -> FallDecision`

**입력값**
- `timestamp_sec`: 현재 프레임 시각
- `decision`: 현재 프레임 낙상 후보 판단 결과

**처리 흐름**
1. 이전 프레임 시각과의 차이 `delta` 계산
2. 현재 시각을 `_previous_timestamp` 에 저장
3. 현재 프레임이 낙상 후보면 `horizontal_streak_seconds += delta`
4. 낙상 후보가 아니면 streak 를 0으로 초기화
5. 누적 시간을 `decision.horizontal_seconds` 에 반영
6. 수정된 `decision` 반환

**반환값**
- 누적 시간이 반영된 `FallDecision`

**부수효과**
- 내부 상태 변경

---

### `build_metrics(self, decision: FallDecision) -> EventMetrics`

**입력값**
- `decision`: 낙상 판단 결과

**처리 흐름**
1. 각도, 지속시간, 포즈 신뢰도, bbox 비율을 `EventMetrics` 로 변환
2. 감지기가 비활성화되어 있으면 `notes["fall_detector"]` 에 이유를 추가

**반환값**
- `EventMetrics`

**부수효과**
- 없음

---

### `should_emit(self, decision: FallDecision) -> bool`

**입력값**
- `decision`: 낙상 판단 결과

**처리 흐름**
1. 감지기가 비활성화 상태면 무조건 `False`
2. 활성화 상태면 `decision.horizontal_seconds >= settings.fall_hold_seconds` 인지 확인

**반환값**
- 이벤트 발행 여부 `bool`

**부수효과**
- 없음

---

# 6. 장시간 무응답 감지기

## app/detectors/inactive.py

### `InactiveDetector.__init__(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. `init_background_subtractor()` 로 배경 차감기 생성
2. `no_motion_seconds = 0.0`
3. 이전 타임스탬프 초기화
4. `_yolo = None`
5. 설정이 켜져 있고 YOLO 패키지가 있으면 `YOLO(settings.yolo_model)` 로 사람 검출 모델 로딩

**반환값**
- 없음

**부수효과**
- OpenCV 배경 차감기 생성
- 선택적으로 YOLO 모델 로딩

---

### `init_background_subtractor(self) -> cv2.BackgroundSubtractor`

**입력값**
- 없음

**처리 흐름**
1. `cv2.createBackgroundSubtractorMOG2(...)` 로 배경 차감기 생성

**반환값**
- OpenCV 배경 차감기 객체

**부수효과**
- 없음

---

### `detect_person(self, frame: np.ndarray) -> tuple[bool, int]`

**입력값**
- `frame`: 현재 프레임

**처리 흐름**
1. YOLO 모델이 없으면 기본값으로 `(True, 1)` 반환
   - 즉, "사람이 있다고 가정"하는 안전한 기본 동작
2. YOLO 모델이 있으면 `predict(frame)` 수행
3. 결과에서 `class_id == 0` 인 객체만 사람으로 카운트
4. `num_persons > 0` 여부와 인원 수 반환

**반환값**
- `(person_present, num_persons)`

**부수효과**
- 선택적으로 YOLO 추론 수행

---

### `calculate_motion(self, frame: np.ndarray) -> float`

**입력값**
- `frame`: 현재 프레임

**처리 흐름**
1. 배경 차감기로 foreground mask 생성
2. 값이 255인 부분만 motion mask 로 정리
3. 3x3 kernel 로 morphology open 적용
4. 움직임 픽셀 수 계산
5. 전체 픽셀 수로 나누어 `motion_ratio` 산출

**반환값**
- `motion_ratio` (`0.0 ~ 1.0` 사이 비율)

**부수효과**
- 배경 차감기 내부 상태 갱신

---

### `accumulate_no_motion(self, timestamp_sec: float, motion_ratio: float, person_present: bool) -> float`

**입력값**
- `timestamp_sec`: 현재 프레임 시각
- `motion_ratio`: 현재 프레임 움직임 비율
- `person_present`: 사람 존재 여부

**처리 흐름**
1. 이전 프레임 시각과의 차이 `delta` 계산
2. 현재 시각을 `_previous_timestamp` 에 저장
3. 사람이 있고, 움직임 비율이 임계치보다 작으면 `no_motion_seconds += delta`
4. 그 외에는 누적 무동작 시간을 0으로 초기화
5. 누적값 반환

**반환값**
- 누적 무동작 시간(초)

**부수효과**
- 내부 상태 변경

---

### `calculate_daily_motion_score(self, motion_values: list[float]) -> float`

**입력값**
- `motion_values`: 여러 프레임/구간의 움직임 비율 리스트

**처리 흐름**
1. 빈 리스트면 `0.0`
2. 아니면 평균을 계산
3. 소수점 6자리로 반올림

**반환값**
- 하루 평균 움직임 점수 `float`

**부수효과**
- 없음

---

### `evaluate(self, frame: np.ndarray, timestamp_sec: float) -> InactiveDecision`

**입력값**
- `frame`: 현재 프레임
- `timestamp_sec`: 현재 프레임 시각

**처리 흐름**
1. `detect_person(frame)` 호출
2. `calculate_motion(frame)` 호출
3. `accumulate_no_motion(timestamp_sec, motion_ratio, person_present)` 호출
4. 위 결과들을 합쳐 `InactiveDecision` 생성

**반환값**
- `InactiveDecision`
  - `motion_ratio`
  - `person_present`
  - `inactive_seconds`
  - `num_persons`

**부수효과**
- 배경 차감기 상태 변경
- 내부 누적 시간 변경

---

### `build_metrics(self, decision: InactiveDecision) -> EventMetrics`

**입력값**
- `decision`: 무응답 판단 결과

**처리 흐름**
1. 움직임 비율, 누적 무동작 시간, 인원 수를 `EventMetrics` 로 포장

**반환값**
- `EventMetrics`

**부수효과**
- 없음

---

### `should_emit(self, decision: InactiveDecision) -> bool`

**입력값**
- `decision`: 무응답 판단 결과

**처리 흐름**
1. 사람이 존재하고
2. `inactive_seconds >= settings.inactive_seconds`
   인지 확인

**반환값**
- 이벤트 발행 여부 `bool`

**부수효과**
- 없음

---

# 7. 폭행 감지 스캐폴드

## app/detectors/violence.py

현재 이 파일은 **확장용 자리**이며 실제 분석 파이프라인에는 연결되어 있지 않다.

### `extract_keypoints(self, frame) -> dict`

**입력값**
- `frame`

**처리 흐름**
- 아직 구현되지 않음
- 빈 딕셔너리 반환

**반환값**
- `{}`

---

### `count_persons(self, frame) -> int`

**입력값**
- `frame`

**처리 흐름**
- 아직 구현되지 않음

**반환값**
- `0`

---

### `calculate_velocity(self, keypoints: dict) -> float`

**입력값**
- `keypoints`

**처리 흐름**
- 아직 구현되지 않음

**반환값**
- `0.0`

---

### `is_violent(self, num_persons: int, velocity: float) -> bool`

**입력값**
- `num_persons`
- `velocity`

**처리 흐름**
1. 사람 수가 2명 이상인지 확인
2. 속도가 0보다 큰지 확인
3. 둘 다 만족하면 `True`

**반환값**
- `bool`

---

### `check_consecutive_frames(self, suspicious: bool) -> int`

**입력값**
- `suspicious`: 현재 프레임이 의심스러운지 여부

**처리 흐름**
1. 의심 프레임이면 `1`
2. 아니면 `0`

**반환값**
- `int`

---

### `build_metrics(self) -> EventMetrics`

**입력값**
- 없음

**처리 흐름**
1. `notes={"status": "scaffold_only"}` 를 담은 `EventMetrics` 생성

**반환값**
- `EventMetrics`

---

# 8. 외부 전송 / 알림

## app/notifier.py

### `EventNotifier.__init__(self, event_store: EventStore | None = None) -> None`

**입력값**
- `event_store`: 주입할 저장소, 없으면 새로 생성

**처리 흐름**
1. 전달된 저장소가 있으면 사용
2. 없으면 `EventStore()` 생성
3. 타임존과 경고 메시지를 `resolve_timezone()` 로 준비

**반환값**
- 없음

**부수효과**
- 저장소 초기화 가능

---

### `send_event(self, event: DetectionEvent) -> NotificationResult`

**입력값**
- `event`: 전송할 감지 이벤트

**처리 흐름**
1. 이벤트를 JSON 직렬화용 딕셔너리로 변환
2. `sent_at` 현재 시각 추가
3. 타임존 경고가 있으면 payload에 추가
4. `settings.spring_boot_event_url` 이 비어 있으면
   1. `event_store.append_outbox(payload)` 실행
   2. "로컬 outbox 저장" 성공 결과 반환
5. URL 이 있으면 재시도 루프 시작
6. 최대 `retry_max_attempts` 만큼 반복
   1. `httpx.Client` 생성
   2. Spring Boot URL 로 POST
   3. 성공 시 성공 결과 반환
   4. 실패 시 에러 문자열 저장 후 backoff sleep
7. 재시도가 모두 실패하면
   1. `last_error` 를 payload에 넣어 outbox에 저장
   2. 실패 결과 반환

**반환값**
- `NotificationResult`
  - `success`
  - `attempts`
  - `detail`

**부수효과**
- 외부 HTTP POST
- 실패 시 outbox JSONL 저장

---

### `get_sleep_time_setting(self, resident_id: int) -> dict`

**입력값**
- `resident_id`: 대상자 ID

**처리 흐름**
1. 수면 설정 조회 URL이 없으면 로컬 기본값 반환
2. URL 이 있으면 GET 요청 수행
3. `residentId` 쿼리 파라미터로 조회
4. 응답 JSON 반환

**반환값**
- 수면 설정 `dict`

**부수효과**
- 외부 HTTP GET 가능

---

### `retry_send(self) -> dict`

**입력값**
- 없음

**처리 흐름**
1. outbox 파일 경로 확인
2. 파일이 없으면 모두 0인 결과 반환
3. 파일이 비어 있어도 모두 0인 결과 반환
4. 파일 각 줄을 읽어 JSON payload 로 복원
5. 각 payload 에 대해
   1. `DetectionEvent.model_validate(payload)` 로 이벤트 복구 시도
   2. `send_event(event)` 호출
   3. 성공하면 succeeded 목록
   4. 실패/예외면 failed 목록
6. 실패 항목만 다시 JSONL 로 outbox 파일에 써서 남김
7. 재시도 통계 반환

**반환값**
- `dict`
  - `retried`
  - `succeeded`
  - `failed`

**부수효과**
- outbox 파일 읽기/쓰기
- 외부 HTTP 재전송 가능

---

# 9. 저장소

## app/storage/event_store.py

### `EventStore.__init__(self, sqlite_path: str | Path | None = None) -> None`

**입력값**
- `sqlite_path`: SQLite 파일 경로, 없으면 설정값 사용

**처리 흐름**
1. 실제 DB 경로 결정
2. 부모 디렉터리 생성
3. `_init_db()` 호출

**반환값**
- 없음

**부수효과**
- 디렉터리 생성
- DB 테이블 초기화

---

### `_connect(self) -> sqlite3.Connection`

**입력값**
- 없음

**처리 흐름**
1. `sqlite3.connect(self.sqlite_path)` 연결 생성
2. `row_factory` 를 `sqlite3.Row` 로 설정

**반환값**
- SQLite 연결 객체

**부수효과**
- DB 연결 생성

---

### `_init_db(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. `_connect()` 로 DB 연결
2. `events` 테이블 생성
3. `capture_records` 테이블 생성
4. 이미 있으면 그대로 둠

**반환값**
- 없음

**부수효과**
- SQLite 스키마 생성

---

### `save_event(self, event: DetectionEvent, capture_record: CaptureRecord | None = None) -> int`

**입력값**
- `event`: 저장할 이벤트
- `capture_record`: 저장된 스냅샷 정보, 없을 수도 있음

**처리 흐름**
1. `events` 테이블에 이벤트 insert
2. 생성된 `event_id` 획득
3. `capture_record` 가 있으면 `capture_records` 테이블에도 insert
4. `event_id` 반환

**반환값**
- 저장된 이벤트의 DB ID (`int`)

**부수효과**
- SQLite insert 수행

---

### `list_events(self) -> list[DetectionEvent]`

**입력값**
- 없음

**처리 흐름**
1. `events` 테이블에서 최신순 조회
2. 각 row를 `_row_to_event(row)` 로 변환
3. 리스트 반환

**반환값**
- `list[DetectionEvent]`

**부수효과**
- SQLite read 수행

---

### `append_outbox(self, payload: dict) -> None`

**입력값**
- `payload`: 전송 실패 또는 보류된 이벤트 데이터

**처리 흐름**
1. outbox 부모 디렉터리 생성
2. JSON 문자열로 변환
3. JSONL 형식으로 한 줄 append

**반환값**
- 없음

**부수효과**
- 파일 append

---

### `_row_to_event(self, row: sqlite3.Row) -> DetectionEvent`

**입력값**
- `row`: SQLite 조회 결과 한 줄

**처리 흐름**
1. `metrics_json` 문자열을 `json.loads()` 로 파싱
2. 열 값을 사용해 `DetectionEvent` 생성
3. `metrics` 는 `EventMetrics.model_validate(...)` 로 복원

**반환값**
- `DetectionEvent`

**부수효과**
- 없음

---

### `bulk_save(self, events: Iterable[tuple[DetectionEvent, CaptureRecord | None]]) -> list[int]`

**입력값**
- `(event, capture_record)` 튜플들의 iterable

**처리 흐름**
1. 빈 `saved_ids` 생성
2. 각 항목마다 `save_event()` 호출
3. 반환된 ID를 리스트에 누적
4. 저장 ID 리스트 반환

**반환값**
- 저장된 이벤트 ID 리스트

**부수효과**
- 여러 건 SQLite insert 수행

---

## app/storage/metrics_logger.py

### `MetricsLogger.__init__(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. `data/metrics` 디렉터리 경로 결정
2. 디렉터리 생성
3. 타임존과 경고 메시지 준비

**반환값**
- 없음

**부수효과**
- 디렉터리 생성

---

### `append(self, resident_id: int, stream_name: str, payload: dict) -> Path`

**입력값**
- `resident_id`: 대상자 ID
- `stream_name`: 예: `"fall"`, `"inactive"`
- `payload`: 기록할 메트릭 데이터

**처리 흐름**
1. 현재 시각 계산
2. 타임존 경고가 있고 payload에 아직 없으면 추가
3. 날짜/스트림/대상자 기준 파일명 생성
4. JSONL 형식으로 한 줄 append

**반환값**
- 로그 파일 경로 `Path`

**부수효과**
- 메트릭 로그 파일 append

---

## app/storage/snapshots.py

### `SnapshotStorage.__init__(self) -> None`

**입력값**
- 없음

**처리 흐름**
1. 스냅샷 기본 디렉터리 저장
2. 타임존과 경고 준비

**반환값**
- 없음

**부수효과**
- 없음

---

### `save(self, frame: np.ndarray, resident_id: int, event_type: EventType, detected_at: datetime) -> CaptureRecord`

**입력값**
- `frame`: 저장할 이미지
- `resident_id`: 대상자 ID
- `event_type`: 이벤트 종류
- `detected_at`: 감지 시각

**처리 흐름**
1. `detected_at` 을 로컬 타임존으로 변환
2. `날짜/resident_id` 구조의 하위 디렉터리 생성
3. 이벤트 종류와 시각을 반영한 파일명 생성
4. `cv2.imwrite()` 로 JPG 저장
5. 저장 실패 시 `RuntimeError` 발생
6. 만료 시각(`snapshot_expire_days`) 계산
7. `CaptureRecord` 생성 후 반환

**반환값**
- `CaptureRecord`

**부수효과**
- 이미지 파일 저장

---

### `cleanup_expired(self, now: datetime | None = None) -> int`

**입력값**
- `now`: 기준 시각, 없으면 현재 시각

**처리 흐름**
1. 기준 시각 결정
2. 스냅샷 디렉터리 아래 모든 `.jpg` 파일 순회
3. 파일 수정 시각을 읽음
4. 만료 기한을 넘긴 파일이면 삭제
5. 삭제 수를 누적
6. 삭제 개수 반환

**반환값**
- 삭제된 파일 수 (`int`)

**부수효과**
- 만료된 스냅샷 파일 삭제

---

# 10. 파일별 핵심 연결 관계

## API 관점 핵심 호출 체인

### `/api/v1/analyze/video`
- `routes.analyze_video()`
  - `VideoAnalyzer.analyze_video()`
    - `VideoReader.read()`
    - 반복:
      - `VideoAnalyzer._process_frame()`
        - `FallDetector.extract_keypoints()`
        - `FallDetector.is_fallen()`
        - `FallDetector.check_duration()`
        - `InactiveDetector.evaluate()`
        - `MetricsLogger.append()`
        - 이벤트 발생 시:
          - `SnapshotStorage.save()`
          - `EventStore.save_event()`
  - 선택적으로 `EventNotifier.send_event()`

### `/api/v1/retry-outbox`
- `routes.retry_outbox()`
  - `EventNotifier.retry_send()`
    - `EventNotifier.send_event()`

---

# 11. 메서드 흐름을 보면서 같이 봐야 할 포인트

## 1) 낙상 감지는 "한 프레임"이 아니라 "지속 시간" 기준
`FallDetector.is_fallen()` 에서 한 번 후보가 되어도 바로 이벤트가 생기지 않는다.  
`check_duration()` 으로 수평 자세가 얼마나 이어졌는지를 누적한 뒤, `should_emit()` 에서 `fall_hold_seconds` 이상일 때만 이벤트가 나온다.

## 2) 무응답 감지도 "사람 있음 + 움직임 적음 + 일정 시간 지속" 조건
`InactiveDetector.evaluate()` 가 `person_present`, `motion_ratio`, `inactive_seconds` 를 묶고,  
`should_emit()` 는 이 누적 시간이 임계치 이상인지 확인한다.

## 3) 이벤트 중복 방지는 `VideoAnalyzer._can_emit()`
같은 종류의 이벤트가 너무 자주 발생하지 않도록 `no_event_cooldown_seconds` 를 둔다.

## 4) 알림 전송 실패 시 바로 버리지 않음
`EventNotifier.send_event()` 는 실패하면 `outbox` JSONL 파일에 저장하고,  
`retry_send()` 로 나중에 재전송할 수 있다.

## 5) 낙상 감지 모델이 없어도 서버는 죽지 않음
`FallDetector.load_model()` 에서 비활성화만 하고,  
`warnings` 와 `health` 에 이유를 남긴다.

---

# 12. 한 줄 정리

이 프로그램의 중심은 **`VideoAnalyzer._process_frame()`** 이다.  
실제 감지 로직은 각 감지기(`FallDetector`, `InactiveDetector`)가 담당하고,  
그 결과를 **로그 저장 → 스냅샷 저장 → DB 저장 → 필요 시 외부 전송** 흐름으로 연결하는 구조다.
