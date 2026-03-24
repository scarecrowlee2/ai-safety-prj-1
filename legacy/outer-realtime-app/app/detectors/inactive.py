from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(slots=True)
class InactiveDecision:
    person_present: bool
    inactive_seconds: float
    motion_ratio: float
    bbox: tuple[int, int, int, int] | None
    should_alert: bool


class InactiveDetector:
    # 이 메서드는 무응답 감지에 필요한 배경 차감기와 사람 검출기를 준비합니다.
    def __init__(self, inactive_seconds: float = 20.0, motion_threshold: float = 0.002):
        self.inactive_seconds_threshold = inactive_seconds
        self.motion_threshold = motion_threshold
        self.no_motion_seconds = 0.0
        self._previous_timestamp: float | None = None
        self.background_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=25,
            detectShadows=True,
        )
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    # 이 메서드는 프레임에서 가장 큰 사람 후보 박스를 찾아 반환합니다.
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

    # 이 메서드는 프레임 전체의 움직임 비율을 계산합니다.
    def calculate_motion(self, frame) -> float:
        fg_mask = self.background_subtractor.apply(frame)
        motion_mask = np.where(fg_mask == 255, 255, 0).astype(np.uint8)
        kernel = np.ones((3, 3), np.uint8)
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, kernel)
        motion_pixels = int(np.count_nonzero(motion_mask == 255))
        total_pixels = motion_mask.shape[0] * motion_mask.shape[1]
        return motion_pixels / max(total_pixels, 1)

    # 이 메서드는 움직임이 적은 시간이 얼마나 누적됐는지 갱신합니다.
    def accumulate(self, timestamp_sec: float, person_present: bool, motion_ratio: float) -> float:
        if self._previous_timestamp is None:
            delta = 0.0
        else:
            delta = max(timestamp_sec - self._previous_timestamp, 0.0)
        self._previous_timestamp = timestamp_sec

        if person_present and motion_ratio < self.motion_threshold:
            self.no_motion_seconds += delta
        else:
            self.no_motion_seconds = 0.0
        return self.no_motion_seconds

    # 이 메서드는 사람 존재 여부와 움직임을 합쳐 무응답 의심 결과를 만듭니다.
    def evaluate(self, frame, timestamp_sec: float) -> InactiveDecision:
        bbox = self.detect_person_box(frame)
        motion_ratio = self.calculate_motion(frame)
        person_present = bbox is not None
        inactive_seconds = self.accumulate(timestamp_sec, person_present, motion_ratio)
        return InactiveDecision(
            person_present=person_present,
            inactive_seconds=inactive_seconds,
            motion_ratio=motion_ratio,
            bbox=bbox,
            should_alert=person_present and inactive_seconds >= self.inactive_seconds_threshold,
        )
