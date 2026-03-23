from __future__ import annotations

from dataclasses import dataclass

import cv2


@dataclass(slots=True)
class FallDecision:
    is_candidate: bool
    should_alert: bool
    horizontal_seconds: float
    bbox_aspect_ratio: float | None
    bbox: tuple[int, int, int, int] | None
    notes: str = ""


class FallDetector:
    # 이 메서드는 낙상 의심 판정에 필요한 상태값과 HOG 사람 검출기를 준비합니다.
    def __init__(self, hold_seconds: float = 3.0, aspect_ratio_threshold: float = 1.15):
        self.hold_seconds = hold_seconds
        self.aspect_ratio_threshold = aspect_ratio_threshold
        self.horizontal_streak_seconds = 0.0
        self._previous_timestamp: float | None = None
        self._last_bbox: tuple[int, int, int, int] | None = None
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    # 이 메서드는 프레임에서 사람으로 보이는 바운딩 박스 후보를 찾습니다.
    def detect_person_box(self, frame) -> tuple[int, int, int, int] | None:
        rects, _weights = self.hog.detectMultiScale(
            frame,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        if len(rects) == 0:
            return None
        rects = sorted(rects, key=lambda r: r[2] * r[3], reverse=True)
        x, y, w, h = rects[0]
        return int(x), int(y), int(w), int(h)

    # 이 메서드는 현재 박스 비율과 유지 시간을 바탕으로 낙상 의심 여부를 계산합니다.
    def evaluate(self, frame, timestamp_sec: float) -> FallDecision:
        bbox = self.detect_person_box(frame)
        if self._previous_timestamp is None:
            delta = 0.0
        else:
            delta = max(timestamp_sec - self._previous_timestamp, 0.0)
        self._previous_timestamp = timestamp_sec

        if bbox is None:
            self.horizontal_streak_seconds = 0.0
            self._last_bbox = None
            return FallDecision(
                is_candidate=False,
                should_alert=False,
                horizontal_seconds=0.0,
                bbox_aspect_ratio=None,
                bbox=None,
                notes="person_not_found",
            )

        x, y, w, h = bbox
        aspect_ratio = w / max(h, 1)
        is_candidate = aspect_ratio >= self.aspect_ratio_threshold

        if is_candidate:
            self.horizontal_streak_seconds += delta
        else:
            self.horizontal_streak_seconds = 0.0

        self._last_bbox = bbox
        return FallDecision(
            is_candidate=is_candidate,
            should_alert=self.horizontal_streak_seconds >= self.hold_seconds,
            horizontal_seconds=self.horizontal_streak_seconds,
            bbox_aspect_ratio=aspect_ratio,
            bbox=bbox,
            notes="hog_bbox_ratio",
        )
