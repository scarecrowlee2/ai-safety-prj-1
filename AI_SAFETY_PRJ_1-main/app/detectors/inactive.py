from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.core.config import settings
from app.schemas import EventMetrics

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - optional runtime dependency
    YOLO = None


@dataclass(slots=True)
class InactiveDecision:
    motion_ratio: float
    person_present: bool
    inactive_seconds: float = 0.0
    num_persons: int = 0


class InactiveDetector:
    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self) -> None:
        self.background_subtractor = self.init_background_subtractor()
        self.no_motion_seconds = 0.0
        self._previous_timestamp: float | None = None
        self._yolo = None
        if settings.enable_yolo_person_gate and YOLO is not None:
            self._yolo = YOLO(settings.yolo_model)

    # 이 메서드는 움직임 계산에 사용할 배경 차감기를 초기화합니다.
    def init_background_subtractor(self) -> cv2.BackgroundSubtractor:
        return cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=25,
            detectShadows=True,
        )

    # 이 메서드는 프레임 안에 사람이 있는지와 사람 수를 추정합니다.
    def detect_person(self, frame: np.ndarray) -> tuple[bool, int]:
        if self._yolo is None:
            return True, 1

        results = self._yolo.predict(frame, verbose=False)
        num_persons = 0
        for result in results:
            if not hasattr(result, "boxes") or result.boxes is None:
                continue
            for cls_id in result.boxes.cls.tolist():
                if int(cls_id) == 0:
                    num_persons += 1
        return num_persons > 0, num_persons

    # 이 메서드는 현재 프레임의 움직임 비율을 계산합니다.
    def calculate_motion(self, frame: np.ndarray) -> float:
        fg_mask = self.background_subtractor.apply(frame)
        motion_mask = np.where(fg_mask == 255, 255, 0).astype(np.uint8)
        kernel = np.ones((3, 3), np.uint8)
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, kernel)
        motion_pixels = int(np.count_nonzero(motion_mask == 255))
        total_pixels = motion_mask.shape[0] * motion_mask.shape[1]
        return motion_pixels / max(total_pixels, 1)

    # 이 메서드는 움직임이 거의 없는 시간을 누적합니다.
    def accumulate_no_motion(self, timestamp_sec: float, motion_ratio: float, person_present: bool) -> float:
        if self._previous_timestamp is None:
            delta = 0.0
        else:
            delta = max(timestamp_sec - self._previous_timestamp, 0.0)
        self._previous_timestamp = timestamp_sec

        if person_present and motion_ratio < settings.motion_threshold:
            self.no_motion_seconds += delta
        else:
            self.no_motion_seconds = 0.0

        return self.no_motion_seconds

    # 이 메서드는 하루 기준의 평균 움직임 점수를 계산합니다.
    def calculate_daily_motion_score(self, motion_values: list[float]) -> float:
        if not motion_values:
            return 0.0
        return round(sum(motion_values) / len(motion_values), 6)

    # 이 메서드는 비활동 상태를 종합 평가해 판정 결과를 만듭니다.
    def evaluate(self, frame: np.ndarray, timestamp_sec: float) -> InactiveDecision:
        person_present, num_persons = self.detect_person(frame)
        motion_ratio = self.calculate_motion(frame)
        inactive_seconds = self.accumulate_no_motion(timestamp_sec, motion_ratio, person_present)
        return InactiveDecision(
            motion_ratio=motion_ratio,
            person_present=person_present,
            inactive_seconds=inactive_seconds,
            num_persons=num_persons,
        )

    # 이 메서드는 감지 결과를 이벤트 메트릭 형태로 정리합니다.
    def build_metrics(self, decision: InactiveDecision) -> EventMetrics:
        return EventMetrics(
            motion_ratio=decision.motion_ratio,
            inactive_seconds=decision.inactive_seconds,
            num_persons=decision.num_persons,
        )

    # 이 메서드는 현재 감지 결과를 실제 이벤트로 발생시킬지 결정합니다.
    def should_emit(self, decision: InactiveDecision) -> bool:
        return decision.person_present and decision.inactive_seconds >= settings.inactive_seconds
