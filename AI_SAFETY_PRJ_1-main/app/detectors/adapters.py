from __future__ import annotations

from dataclasses import asdict

from app.detectors.contracts import DetectorInput, DetectorResult, OverlayAnnotation
from app.detectors.fall import FallDetector
from app.detectors.inactive import InactiveDetector
from app.detectors.violence import ViolenceDetector


def run_fall_detector(detector: FallDetector, detector_input: DetectorInput) -> DetectorResult:
    timestamp_ms = int(detector_input.timestamp_sec * 1000)
    keypoints = detector.extract_keypoints(detector_input.frame, timestamp_ms)
    decision = detector.is_fallen(keypoints)
    decision = detector.check_duration(detector_input.timestamp_sec, decision)
    detected = detector.should_emit(decision)

    return DetectorResult(
        detector="fall",
        event_type="fall",
        detected=detected,
        label="FALL" if detected else ("FALL_WATCH" if decision.is_candidate else "NORMAL"),
        score=decision.pose_confidence,
        metadata=asdict(decision),
        raw_decision=decision,
    )


def run_inactive_detector(detector: InactiveDetector, detector_input: DetectorInput) -> DetectorResult:
    decision = detector.evaluate(detector_input.frame, detector_input.timestamp_sec)
    detected = detector.should_emit(decision)

    return DetectorResult(
        detector="inactive",
        event_type="inactive",
        detected=detected,
        label="INACTIVE" if detected else ("INACTIVE_WATCH" if decision.person_present else "NO_PERSON"),
        score=1.0 - decision.motion_ratio,
        metadata=asdict(decision),
        raw_decision=decision,
    )


def run_violence_detector(detector: ViolenceDetector, detector_input: DetectorInput) -> DetectorResult:
    decision = detector.evaluate(detector_input.frame, detector_input.timestamp_sec)
    detected = detector.should_emit(decision)

    box_color = (255, 0, 255) if detected else (180, 0, 255)
    overlays = [
        OverlayAnnotation(
            label=f"P{index + 1}",
            color_bgr=box_color,
            box_xyxy=(x, y, x + w, y + h),
        )
        for index, (x, y, w, h) in enumerate(decision.boxes)
    ]

    return DetectorResult(
        detector="violence",
        event_type="violence",
        detected=detected,
        label="VIOLENCE" if detected else ("VIOLENCE_WATCH" if decision.num_persons >= 2 else "NORMAL"),
        score=decision.motion_ratio,
        overlays=overlays,
        metadata=asdict(decision),
        raw_decision=decision,
    )
