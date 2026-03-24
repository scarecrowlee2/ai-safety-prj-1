from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import math

import numpy as np

from app.schemas import EventMetrics

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None


@dataclass(slots=True)
class ViolenceDecision:
    num_persons: int
    motion_ratio: float
    close_pairs: int
    suspicious_seconds: float
    should_alert: bool
    boxes: list[tuple[int, int, int, int]]


class ViolenceDetector:
    # 이 메서드는 다인원 근접과 큰 움직임 기반 폭행 의심 판정을 위한 상태를 준비합니다.
    def __init__(
        self,
        motion_threshold: float = 0.025,
        pair_distance_threshold: float = 220.0,
        hold_seconds: float = 2.0,
    ) -> None:
        self.motion_threshold = motion_threshold
        self.pair_distance_threshold = pair_distance_threshold
        self.hold_seconds = hold_seconds
        self.suspicious_seconds = 0.0
        self._previous_timestamp: float | None = None

        self.enabled = False
        self.disabled_reason = ""
        self.background_subtractor = None
        self.hog = None
        self._initialize()

    # 이 메서드는 감지기에 필요한 OpenCV 리소스를 초기화합니다.
    def _initialize(self) -> None:
        if cv2 is None:
            self.enabled = False
            self.disabled_reason = "opencv unavailable"
            return

        self.background_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=18,
            detectShadows=False,
        )
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.enabled = True
        self.disabled_reason = ""

    # 이 메서드는 감지기의 현재 활성화 상태와 설정값을 반환합니다.
    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": "opencv_hog_mog2",
            "reason": self.disabled_reason,
            "motion_threshold": self.motion_threshold,
            "pair_distance_threshold": self.pair_distance_threshold,
            "hold_seconds": self.hold_seconds,
        }

    # 이 메서드는 프레임 안의 사람 후보 박스 목록을 반환합니다.
    def detect_person_boxes(self, frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        if not self.enabled or self.hog is None:
            return []

        rects, _weights = self.hog.detectMultiScale(
            frame,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        boxes = []
        for x, y, w, h in rects:
            boxes.append((int(x), int(y), int(w), int(h)))
        boxes.sort(key=lambda r: r[2] * r[3], reverse=True)
        return boxes[:4]

    # 이 메서드는 프레임 전체의 움직임 강도를 비율 값으로 계산합니다.
    def calculate_motion(self, frame: np.ndarray) -> float:
        if not self.enabled or self.background_subtractor is None or cv2 is None:
            return 0.0

        fg_mask = self.background_subtractor.apply(frame)
        motion_mask = np.where(fg_mask == 255, 255, 0).astype(np.uint8)
        kernel = np.ones((5, 5), np.uint8)
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, kernel)
        motion_pixels = int(np.count_nonzero(motion_mask == 255))
        total_pixels = motion_mask.shape[0] * motion_mask.shape[1]
        return motion_pixels / max(total_pixels, 1)

    # 이 메서드는 사람 중심점이 서로 가까운 쌍의 개수를 계산합니다.
    def count_close_pairs(self, boxes: list[tuple[int, int, int, int]]) -> int:
        centers = []
        for x, y, w, h in boxes:
            centers.append((x + w / 2.0, y + h / 2.0))

        close_pairs = 0
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                distance = math.dist(centers[i], centers[j])
                if distance <= self.pair_distance_threshold:
                    close_pairs += 1
        return close_pairs

    # 이 메서드는 의심 조건이 몇 초 동안 이어졌는지 누적합니다.
    def accumulate(self, timestamp_sec: float, suspicious: bool) -> float:
        if self._previous_timestamp is None:
            delta = 0.0
        else:
            delta = max(timestamp_sec - self._previous_timestamp, 0.0)
        self._previous_timestamp = timestamp_sec

        if suspicious:
            self.suspicious_seconds += delta
        else:
            self.suspicious_seconds = 0.0
        return self.suspicious_seconds

    # 이 메서드는 다중 인원과 큰 움직임을 함께 평가해 폭행 의심 결과를 만듭니다.
    def evaluate(self, frame: np.ndarray, timestamp_sec: float) -> ViolenceDecision:
        if not self.enabled:
            return ViolenceDecision(
                num_persons=0,
                motion_ratio=0.0,
                close_pairs=0,
                suspicious_seconds=0.0,
                should_alert=False,
                boxes=[],
            )

        boxes = self.detect_person_boxes(frame)
        motion_ratio = self.calculate_motion(frame)
        close_pairs = self.count_close_pairs(boxes)
        suspicious = len(boxes) >= 2 and close_pairs >= 1 and motion_ratio >= self.motion_threshold
        suspicious_seconds = self.accumulate(timestamp_sec, suspicious)
        return ViolenceDecision(
            num_persons=len(boxes),
            motion_ratio=motion_ratio,
            close_pairs=close_pairs,
            suspicious_seconds=suspicious_seconds,
            should_alert=suspicious_seconds >= self.hold_seconds,
            boxes=boxes,
        )

    # 이 메서드는 감지 결과를 이벤트 메트릭 형태로 정리합니다.
    def build_metrics(self, decision: ViolenceDecision) -> EventMetrics:
        metrics = EventMetrics(
            motion_ratio=decision.motion_ratio,
            num_persons=decision.num_persons,
            notes={
                "close_pairs": decision.close_pairs,
                "suspicious_seconds": decision.suspicious_seconds,
            },
        )
        if not self.enabled and self.disabled_reason:
            metrics.notes["violence_detector"] = self.disabled_reason
        return metrics

    # 이 메서드는 현재 감지 결과를 실제 이벤트로 발생시킬지 결정합니다.
    def should_emit(self, decision: ViolenceDecision) -> bool:
        return self.enabled and decision.should_alert
