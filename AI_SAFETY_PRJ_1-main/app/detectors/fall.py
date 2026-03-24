from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import math

import numpy as np

from app.core.config import settings
from app.schemas import EventMetrics

try:
    import mediapipe as mp
except Exception:  # pragma: no cover - optional runtime dependency
    mp = None

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None


@dataclass(slots=True)
class FallDecision:
    is_candidate: bool
    pose_confidence: float
    torso_angle_from_vertical_deg: float | None
    bbox_aspect_ratio: float | None
    horizontal_seconds: float = 0.0


class FallDetector:
    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self) -> None:
        self.landmarker = None
        self.hog = None
        self.enabled = False
        self.disabled_reason = ""
        self.backend = "none"
        self.horizontal_streak_seconds = 0.0
        self._previous_timestamp: float | None = None
        self.load_model()

    # 이 메서드는 낙상 감지에 필요한 모델과 백엔드를 로드합니다.
    def load_model(self) -> None:
        self.close()

        if not settings.fall_enabled:
            self._disable("fall detector disabled by configuration")
            return

        if self._try_init_pose_backend():
            return

        if settings.fall_enable_hog_fallback and self._try_init_hog_backend():
            return

        if not self.disabled_reason:
            self._disable("fall detector backend unavailable")

    def _try_init_pose_backend(self) -> bool:
        if mp is None:
            self._disable("mediapipe package unavailable")
            return False

        if not hasattr(mp, "tasks") or not hasattr(mp.tasks, "vision"):
            self._disable("mediapipe tasks api unavailable")
            return False

        model_path = Path(settings.fall_pose_task_model_path)
        if not model_path.exists():
            self._disable(f"pose task model not found: {model_path}")
            return False

        try:
            base_options = mp.tasks.BaseOptions(model_asset_path=str(model_path))
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=settings.fall_min_pose_detection_confidence,
                min_pose_presence_confidence=settings.fall_min_pose_presence_confidence,
                min_tracking_confidence=settings.fall_min_tracking_confidence,
                output_segmentation_masks=False,
            )
            self.landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
            self.enabled = True
            self.backend = "mediapipe_tasks"
            self.disabled_reason = ""
            return True
        except Exception as exc:  # pragma: no cover - runtime/environment dependent
            self._disable(f"failed to initialize pose landmarker: {exc}")
            return False

    def _try_init_hog_backend(self) -> bool:
        if cv2 is None:
            self._disable(f"{self.disabled_reason}; opencv unavailable")
            return False

        try:
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self.enabled = True
            self.backend = "hog_fallback"
            self.disabled_reason = ""
            return True
        except Exception as exc:  # pragma: no cover - runtime/environment dependent
            self._disable(f"{self.disabled_reason}; failed to initialize hog fallback: {exc}")
            return False

    # 이 메서드는 감지기를 비활성화하고 사유를 기록합니다.
    def _disable(self, reason: str) -> None:
        self.enabled = False
        self.disabled_reason = reason
        self.backend = "none"
        self.landmarker = None
        self.hog = None

    # 이 메서드는 모델이나 리소스를 안전하게 정리합니다.
    def close(self) -> None:
        if self.landmarker is not None and hasattr(self.landmarker, "close"):
            self.landmarker.close()
        self.landmarker = None
        self.hog = None

    # 이 메서드는 감지기의 현재 활성화 상태와 사유를 반환합니다.
    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "model_path": str(settings.fall_pose_task_model_path),
            "reason": self.disabled_reason,
            "hog_fallback_enabled": settings.fall_enable_hog_fallback,
        }

    # 이 메서드는 프레임에서 사람의 핵심 좌표 정보를 추출합니다.
    def extract_keypoints(self, frame: np.ndarray, timestamp_ms: int) -> dict[str, Any] | None:
        if self.backend == "hog_fallback":
            return self._extract_hog_detection(frame)

        if self.landmarker is None or mp is None or cv2 is None:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)
        pose_landmarks = getattr(result, "pose_landmarks", None) or []
        if not pose_landmarks:
            return None

        image_h, image_w = frame.shape[:2]
        landmarks = pose_landmarks[0]

        points: dict[str, tuple[float, float, float]] = {}
        confidences: list[float] = []
        for idx, lm in enumerate(landmarks):
            x = float(lm.x * image_w)
            y = float(lm.y * image_h)
            z = float(lm.z)
            points[str(idx)] = (x, y, z)
            visibility = float(getattr(lm, "visibility", 0.0))
            presence = float(getattr(lm, "presence", 1.0))
            confidences.append(min(visibility, presence))

        return {
            "landmarks": landmarks,
            "points": points,
            "mean_visibility": sum(confidences) / max(len(confidences), 1),
            "image_size": (image_w, image_h),
        }

    def _extract_hog_detection(self, frame: np.ndarray) -> dict[str, Any] | None:
        if self.hog is None:
            return None
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
        return {
            "bbox": (int(x), int(y), int(w), int(h)),
            "bbox_aspect_ratio": float(w / max(h, 1)),
            "mean_visibility": 1.0,
        }

    # 이 메서드는 특정 랜드마크 좌표를 이미지 기준 점으로 변환합니다.
    def _landmark_point(
        self,
        landmarks: list[Any],
        index: int,
        image_w: int,
        image_h: int,
    ) -> tuple[float, float, float, float]:
        lm = landmarks[index]
        visibility = float(getattr(lm, "visibility", 0.0))
        presence = float(getattr(lm, "presence", 1.0))
        confidence = min(visibility, presence)
        return float(lm.x * image_w), float(lm.y * image_h), float(lm.z), confidence

    # 이 메서드는 추출된 자세 정보를 바탕으로 낙상 여부를 판정합니다.
    def is_fallen(self, keypoints: dict[str, Any] | None) -> FallDecision:
        if self.backend == "hog_fallback":
            return self._is_fallen_hog(keypoints)
        return self._is_fallen_pose(keypoints)

    def _is_fallen_hog(self, keypoints: dict[str, Any] | None) -> FallDecision:
        if not keypoints:
            return FallDecision(False, 0.0, None, None)

        aspect_ratio = float(keypoints["bbox_aspect_ratio"])
        is_candidate = aspect_ratio >= settings.fall_hog_aspect_ratio_threshold
        return FallDecision(
            is_candidate=is_candidate,
            pose_confidence=1.0,
            torso_angle_from_vertical_deg=None,
            bbox_aspect_ratio=aspect_ratio,
        )

    def _is_fallen_pose(self, keypoints: dict[str, Any] | None) -> FallDecision:
        if not keypoints:
            return FallDecision(False, 0.0, None, None)

        landmarks = keypoints["landmarks"]
        image_w, image_h = keypoints["image_size"]
        pose_confidence = float(keypoints["mean_visibility"])

        if pose_confidence < settings.fall_min_visibility:
            return FallDecision(False, pose_confidence, None, None)

        left_shoulder = self._landmark_point(landmarks, 11, image_w, image_h)
        right_shoulder = self._landmark_point(landmarks, 12, image_w, image_h)
        left_hip = self._landmark_point(landmarks, 23, image_w, image_h)
        right_hip = self._landmark_point(landmarks, 24, image_w, image_h)

        shoulder_center = ((left_shoulder[0] + right_shoulder[0]) / 2.0, (left_shoulder[1] + right_shoulder[1]) / 2.0)
        hip_center = ((left_hip[0] + right_hip[0]) / 2.0, (left_hip[1] + right_hip[1]) / 2.0)

        dx = shoulder_center[0] - hip_center[0]
        dy = shoulder_center[1] - hip_center[1]
        torso_angle_from_vertical_deg = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))

        xs: list[float] = []
        ys: list[float] = []
        for lm in landmarks:
            confidence = min(float(getattr(lm, "visibility", 0.0)), float(getattr(lm, "presence", 1.0)))
            if confidence >= settings.fall_min_visibility:
                xs.append(float(lm.x * image_w))
                ys.append(float(lm.y * image_h))

        bbox_aspect_ratio = None
        if xs and ys:
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            bbox_aspect_ratio = width / max(height, 1.0)

        is_candidate = torso_angle_from_vertical_deg >= settings.fall_angle_threshold_deg
        if bbox_aspect_ratio is not None and bbox_aspect_ratio >= 1.2:
            is_candidate = is_candidate or torso_angle_from_vertical_deg >= (settings.fall_angle_threshold_deg - 10)

        return FallDecision(
            is_candidate=is_candidate,
            pose_confidence=pose_confidence,
            torso_angle_from_vertical_deg=torso_angle_from_vertical_deg,
            bbox_aspect_ratio=bbox_aspect_ratio,
        )

    # 이 메서드는 낙상 자세가 일정 시간 이상 유지됐는지 확인합니다.
    def check_duration(self, timestamp_sec: float, decision: FallDecision) -> FallDecision:
        if self._previous_timestamp is None:
            delta = 0.0
        else:
            delta = max(timestamp_sec - self._previous_timestamp, 0.0)
        self._previous_timestamp = timestamp_sec

        if decision.is_candidate:
            self.horizontal_streak_seconds += delta
        else:
            self.horizontal_streak_seconds = 0.0

        decision.horizontal_seconds = self.horizontal_streak_seconds
        return decision

    # 이 메서드는 감지 결과를 이벤트 메트릭 형태로 정리합니다.
    def build_metrics(self, decision: FallDecision) -> EventMetrics:
        metrics = EventMetrics(
            torso_angle_from_vertical_deg=decision.torso_angle_from_vertical_deg,
            horizontal_seconds=decision.horizontal_seconds,
            pose_confidence=decision.pose_confidence,
            bbox_aspect_ratio=decision.bbox_aspect_ratio,
        )
        if not self.enabled and self.disabled_reason:
            metrics.notes["fall_detector"] = self.disabled_reason
        if self.backend == "hog_fallback":
            metrics.notes["fall_backend"] = "hog_fallback"
        return metrics

    # 이 메서드는 현재 감지 결과를 실제 이벤트로 발생시킬지 결정합니다.
    def should_emit(self, decision: FallDecision) -> bool:
        return self.enabled and decision.horizontal_seconds >= settings.fall_hold_seconds
