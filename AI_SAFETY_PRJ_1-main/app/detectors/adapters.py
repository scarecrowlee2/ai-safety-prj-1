from __future__ import annotations

from dataclasses import asdict

from app.detectors.contracts import DetectorInput, DetectorResult
from app.detectors.fall import FallDetector
from app.detectors.inactive import InactiveDetector
from app.detectors.violence import ViolenceDecision, ViolenceDetector


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
    keypoints = detector.extract_keypoints(detector_input.frame)
    num_persons = detector.count_persons(detector_input.frame)
    max_velocity = detector.calculate_velocity(keypoints)
    suspicious = detector.is_violent(num_persons, max_velocity)
    suspicious_frames = detector.check_consecutive_frames(suspicious)
    decision = ViolenceDecision(num_persons=num_persons, max_velocity=max_velocity, suspicious_frames=suspicious_frames)

    detected = suspicious_frames >= 2
    return DetectorResult(
        detector="violence",
        event_type="violence",
        detected=detected,
        label="VIOLENCE" if detected else ("VIOLENCE_WATCH" if num_persons >= 2 else "NORMAL"),
        score=max_velocity,
        metadata=asdict(decision),
        raw_decision=decision,
    )
