from __future__ import annotations

import numpy as np
import pytest

from app.core.config import settings
from app.detectors.inactive import InactiveDetector


@pytest.fixture
def detector(monkeypatch) -> InactiveDetector:
    monkeypatch.setattr(InactiveDetector, "init_background_subtractor", lambda self: object())
    return InactiveDetector()


def test_detect_person_without_yolo_returns_no_person(detector) -> None:
    frame = np.zeros((8, 8, 3), dtype=np.uint8)

    person_present, num_persons, bbox = detector.detect_person(frame)

    assert person_present is False
    assert num_persons == 0
    assert bbox is None


def test_evaluate_does_not_accumulate_when_no_person(monkeypatch, detector) -> None:
    monkeypatch.setattr(detector, "detect_person", lambda _frame: (False, 0, None))
    monkeypatch.setattr(detector, "calculate_motion", lambda _frame: 0.0)
    frame = np.zeros((8, 8, 3), dtype=np.uint8)

    first = detector.evaluate(frame, 10.0)
    second = detector.evaluate(frame, 15.0)
    third = detector.evaluate(frame, 20.0)

    assert first.person_present is False
    assert second.person_present is False
    assert third.person_present is False
    assert first.inactive_seconds == 0.0
    assert second.inactive_seconds == 0.0
    assert third.inactive_seconds == 0.0
    assert detector.no_motion_seconds == 0.0


def test_evaluate_accumulates_when_person_present_and_still(monkeypatch, detector) -> None:
    monkeypatch.setattr(detector, "detect_person", lambda _frame: (True, 1, (0, 0, 4, 4)))
    monkeypatch.setattr(detector, "calculate_motion", lambda _frame: 0.0)
    monkeypatch.setattr(settings, "motion_threshold", 0.05)
    frame = np.zeros((8, 8, 3), dtype=np.uint8)

    first = detector.evaluate(frame, 100.0)
    second = detector.evaluate(frame, 104.5)
    third = detector.evaluate(frame, 110.0)

    assert first.inactive_seconds == pytest.approx(0.0)
    assert second.inactive_seconds == pytest.approx(4.5)
    assert third.inactive_seconds == pytest.approx(10.0)
    assert detector.no_motion_seconds == pytest.approx(10.0)


def test_evaluate_resets_when_person_moves(monkeypatch, detector) -> None:
    monkeypatch.setattr(detector, "detect_person", lambda _frame: (True, 1, (0, 0, 4, 4)))
    motion_values = iter([0.0, 0.0, 0.2, 0.0])
    monkeypatch.setattr(detector, "calculate_motion", lambda _frame: next(motion_values))
    monkeypatch.setattr(settings, "motion_threshold", 0.05)
    frame = np.zeros((8, 8, 3), dtype=np.uint8)

    first = detector.evaluate(frame, 0.0)
    second = detector.evaluate(frame, 3.0)
    third = detector.evaluate(frame, 7.0)
    fourth = detector.evaluate(frame, 9.0)

    assert first.inactive_seconds == pytest.approx(0.0)
    assert second.inactive_seconds == pytest.approx(3.0)
    assert third.inactive_seconds == pytest.approx(0.0)
    assert fourth.inactive_seconds == pytest.approx(2.0)
