from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable

from app.core.config import settings
from app.core.timeutils import resolve_timezone
from app.core.video import VideoReader
from app.detectors.adapters import run_fall_detector, run_inactive_detector
from app.detectors.contracts import DetectorInput
from app.detectors.fall import FallDetector
from app.detectors.inactive import InactiveDetector
from app.schemas import AnalyzeVideoResponse, DetectionEvent, EventType
from app.storage.event_store import EventStore
from app.storage.metrics_logger import MetricsLogger
from app.storage.snapshots import SnapshotStorage


class VideoAnalyzer:
    UPLOAD_SUPPORTED_DETECTORS: tuple[str, ...] = ("fall", "inactive")
    REALTIME_ONLY_DETECTORS: tuple[str, ...] = ("violence",)

    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self) -> None:
        self.tz, self.timezone_warning = resolve_timezone(settings.app_timezone)
        self.fall_detector = FallDetector()
        self.inactive_detector = InactiveDetector()
        self.snapshot_storage = SnapshotStorage()
        self.event_store = EventStore()
        self.metrics_logger = MetricsLogger()
        self._last_emitted_at: dict[EventType, float] = {}
        self._analyze_lock = Lock()

    # 이 메서드는 현재 감지기 상태와 경고 정보를 진단용으로 반환합니다.
    def diagnostics(self) -> dict:
        warnings = self._build_warnings()
        fall_status = self.fall_detector.status()
        inactive_status = self.inactive_detector.status()
        unsupported_detectors = {
            detector_name: {
                "supported": False,
                "enabled": False,
                "mode": "unsupported",
                "reason": "not implemented in upload analyzer (available in realtime pipeline only)",
            }
            for detector_name in self.REALTIME_ONLY_DETECTORS
        }

        return {
            "analyzer": {
                "name": "upload_video_analyzer",
                "pipeline_scope": "upload",
            },
            "timezone": settings.app_timezone,
            "warnings": warnings,
            "capabilities": {
                "upload_supported_detectors": list(self.UPLOAD_SUPPORTED_DETECTORS),
                "upload_unsupported_detectors": list(self.REALTIME_ONLY_DETECTORS),
                "realtime_pipeline_detectors": [*self.UPLOAD_SUPPORTED_DETECTORS, *self.REALTIME_ONLY_DETECTORS],
            },
            "detectors": {
                "fall": {
                    "supported": True,
                    **fall_status,
                },
                "inactive": {
                    "supported": True,
                    **inactive_status,
                },
                **unsupported_detectors,
            },
        }

    # 이 함수는 영상을 분석해 감지 이벤트 목록과 부가 정보를 생성합니다.
    def analyze_video(self, resident_id: int, video_path: str | Path) -> AnalyzeVideoResponse:
        with self._analyze_lock:
            self.reset_runtime_state()
            reader = VideoReader(video_path=video_path, sample_fps=settings.sample_fps)
            _metadata, frames = reader.read()
            events: list[DetectionEvent] = []

            for frame in frames:
                frame_events = self._process_frame(
                    resident_id=resident_id,
                    frame_image=frame.image,
                    timestamp_sec=frame.timestamp_sec,
                )
                events.extend(frame_events)

            return AnalyzeVideoResponse(
                resident_id=resident_id,
                video_name=Path(video_path).name,
                events=events,
                warnings=self._build_warnings(),
            )

    # 이 메서드는 분석 요청 간 누적 상태를 초기화합니다.
    def reset_runtime_state(self) -> None:
        self._last_emitted_at.clear()
        self.fall_detector.reset_runtime_state()
        self.inactive_detector.reset_runtime_state()

    # 이 메서드는 현재 설정과 감지기 상태를 바탕으로 경고 메시지를 정리합니다.
    def _build_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.timezone_warning:
            warnings.append(self.timezone_warning)
        if not self.fall_detector.enabled and self.fall_detector.disabled_reason:
            warnings.append(f"fall detector disabled: {self.fall_detector.disabled_reason}")
        inactive_status = self.inactive_detector.status()
        inactive_mode = inactive_status.get("mode", "unknown")
        if not self.inactive_detector.enabled and self.inactive_detector.disabled_reason:
            warnings.append(f"inactive detector disabled: {self.inactive_detector.disabled_reason}")
        if inactive_mode == "degraded":
            warnings.append(
                "inactive detector degraded: person gate disabled "
                "(set ENABLE_YOLO_PERSON_GATE=true for production full mode)"
            )
        if inactive_mode == "error":
            warnings.append("inactive detector error: person gate required but not ready")
        return warnings

    # 이 메서드는 단일 프레임을 분석해 이벤트 발생 여부를 판단합니다.
    def _process_frame(self, resident_id: int, frame_image, timestamp_sec: float) -> list[DetectionEvent]:
        emitted: list[DetectionEvent] = []

        detected_at = datetime.now(self.tz)
        timestamp_ms = int(round(timestamp_sec * 1000))

        detector_input = DetectorInput(frame=frame_image, timestamp_sec=timestamp_sec)

        fall_result = run_fall_detector(self.fall_detector, detector_input)
        fall_decision = fall_result.raw_decision

        self.metrics_logger.append(
            resident_id=resident_id,
            stream_name="fall",
            payload={
                "timestamp_sec": timestamp_sec,
                "timestamp_ms": timestamp_ms,
                "event_type": "FALL",
                "detector_enabled": self.fall_detector.enabled,
                "detector_reason": self.fall_detector.disabled_reason,
                "pose_confidence": fall_decision.pose_confidence,
                "torso_angle_from_vertical_deg": fall_decision.torso_angle_from_vertical_deg,
                "bbox_aspect_ratio": fall_decision.bbox_aspect_ratio,
                "horizontal_seconds": fall_decision.horizontal_seconds,
            },
        )

        if fall_result.detected and self._can_emit(EventType.FALL, timestamp_sec):
            capture_record = self.snapshot_storage.save(frame_image, resident_id, EventType.FALL, detected_at)
            event = DetectionEvent(
                resident_id=resident_id,
                event_type=EventType.FALL,
                detected_at=detected_at,
                snapshot_path=capture_record.file_path,
                description="horizontal posture sustained",
                metrics=self.fall_detector.build_metrics(fall_decision),
            )
            self.event_store.save_event(event, capture_record)
            emitted.append(event)
            self._mark_emitted(EventType.FALL, timestamp_sec)
            self.fall_detector.horizontal_streak_seconds = 0.0

        inactive_result = run_inactive_detector(self.inactive_detector, detector_input)
        inactive_decision = inactive_result.raw_decision
        self.metrics_logger.append(
            resident_id=resident_id,
            stream_name="inactive",
            payload={
                "timestamp_sec": timestamp_sec,
                "event_type": "INACTIVE",
                "person_present": inactive_decision.person_present,
                "num_persons": inactive_decision.num_persons,
                "motion_ratio": inactive_decision.motion_ratio,
                "inactive_seconds": inactive_decision.inactive_seconds,
            },
        )

        if inactive_result.detected and self._can_emit(EventType.INACTIVE, timestamp_sec):
            capture_record = self.snapshot_storage.save(frame_image, resident_id, EventType.INACTIVE, detected_at)
            event = DetectionEvent(
                resident_id=resident_id,
                event_type=EventType.INACTIVE,
                detected_at=detected_at,
                snapshot_path=capture_record.file_path,
                description="motion below threshold for sustained duration",
                metrics=self.inactive_detector.build_metrics(inactive_decision),
            )
            self.event_store.save_event(event, capture_record)
            emitted.append(event)
            self._mark_emitted(EventType.INACTIVE, timestamp_sec)
            self.inactive_detector.no_motion_seconds = 0.0

        return emitted

    # 이 메서드는 같은 유형의 이벤트를 지금 다시 발생시켜도 되는지 확인합니다.
    def _can_emit(self, event_type: EventType, timestamp_sec: float) -> bool:
        last_ts = self._last_emitted_at.get(event_type)
        if last_ts is None:
            return True
        return (timestamp_sec - last_ts) >= settings.no_event_cooldown_seconds

    # 이 메서드는 특정 이벤트가 발생한 시점을 기록합니다.
    def _mark_emitted(self, event_type: EventType, timestamp_sec: float) -> None:
        self._last_emitted_at[event_type] = timestamp_sec


_analyzer_lock = Lock()
_shared_analyzer: VideoAnalyzer | None = None
_shared_analyzer_factory: Callable[[], VideoAnalyzer] | None = None


def get_video_analyzer(factory: Callable[[], VideoAnalyzer] | None = None) -> VideoAnalyzer:
    selected_factory = factory or VideoAnalyzer
    global _shared_analyzer, _shared_analyzer_factory
    with _analyzer_lock:
        if _shared_analyzer is None or _shared_analyzer_factory is not selected_factory:
            _shared_analyzer = selected_factory()
            _shared_analyzer_factory = selected_factory
        return _shared_analyzer
