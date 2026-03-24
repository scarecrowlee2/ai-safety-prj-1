from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from app.detectors.fall import FallDecision, FallDetector
from app.detectors.inactive import InactiveDecision, InactiveDetector
from app.detectors.violence import ViolenceDecision, ViolenceDetector
from app.storage.event_logger import EventLogger


@dataclass(slots=True)
class RealtimePipelineResult:
    """Processed frame plus structured metadata for realtime stream consumers."""

    frame: np.ndarray
    metadata: dict[str, Any]


class RealtimePipeline:
    """Realtime frame-processing coordinator used by streaming routes."""

    def __init__(
        self,
        event_log_path: str = "data/realtime_events.jsonl",
        event_logger: EventLogger | None = None,
    ) -> None:
        self.fall_detector = FallDetector()
        self.inactive_detector = InactiveDetector()
        self.violence_detector = ViolenceDetector()
        self.event_logger = event_logger or EventLogger(event_log_path)

        self.last_alert_state = {"fall": False, "inactive": False, "violence": False}
        self._cv2 = None

        self.overlay_colors = {
            "safe": (0, 220, 0),
            "fall_watch": (0, 200, 255),
            "fall_alert": (0, 0, 255),
            "inactive_watch": (255, 200, 0),
            "inactive_alert": (0, 140, 255),
            "violence_watch": (180, 0, 255),
            "violence_alert": (255, 0, 255),
            "text": (255, 255, 255),
            "panel": (25, 25, 25),
        }

    def _get_cv2(self):
        if self._cv2 is None:
            import cv2

            self._cv2 = cv2
        return self._cv2

    def process_frame(self, frame: np.ndarray, timestamp_sec: float) -> RealtimePipelineResult:
        """Run realtime detectors, draw overlays, and return frame + metadata."""

        overlay = frame.copy()

        fall = self.fall_detector.check_duration(
            timestamp_sec,
            self.fall_detector.is_fallen(self.fall_detector.extract_keypoints(frame, int(timestamp_sec * 1000))),
        )
        inactive = self.inactive_detector.evaluate(frame, timestamp_sec)
        violence = self._evaluate_violence(frame)

        states = self._build_state_flags(fall=fall, inactive=inactive, violence=violence)
        self._log_new_alerts(fall=fall, inactive=inactive, violence=violence, states=states, timestamp_sec=timestamp_sec)

        self._draw_overlay(overlay=overlay, states=states, fall=fall, inactive=inactive, violence=violence)

        metadata = {
            "timestamp_sec": timestamp_sec,
            "states": states,
            "events": self._event_metadata(states),
            "detections": {
                "fall": asdict(fall),
                "inactive": asdict(inactive),
                "violence": asdict(violence),
            },
        }
        return RealtimePipelineResult(frame=overlay, metadata=metadata)

    def _evaluate_violence(self, frame: np.ndarray) -> ViolenceDecision:
        keypoints = self.violence_detector.extract_keypoints(frame)
        num_persons = self.violence_detector.count_persons(frame)
        max_velocity = self.violence_detector.calculate_velocity(keypoints)
        suspicious = self.violence_detector.is_violent(num_persons, max_velocity)
        suspicious_frames = self.violence_detector.check_consecutive_frames(suspicious)
        return ViolenceDecision(num_persons=num_persons, max_velocity=max_velocity, suspicious_frames=suspicious_frames)

    def _build_state_flags(
        self,
        *,
        fall: FallDecision,
        inactive: InactiveDecision,
        violence: ViolenceDecision,
    ) -> dict[str, bool]:
        fall_alert = self.fall_detector.should_emit(fall)
        inactive_alert = self.inactive_detector.should_emit(inactive)
        violence_alert = violence.suspicious_frames >= 2

        return {
            "fall_alert": fall_alert,
            "fall_watch": fall.is_candidate and not fall_alert,
            "inactive_alert": inactive_alert,
            "inactive_watch": inactive.person_present and not inactive_alert,
            "violence_alert": violence_alert,
            "violence_watch": (violence.num_persons >= 2) and not violence_alert,
        }

    def _draw_overlay(
        self,
        *,
        overlay: np.ndarray,
        states: dict[str, bool],
        fall: FallDecision,
        inactive: InactiveDecision,
        violence: ViolenceDecision,
    ) -> None:
        y = self._draw_status_panel(overlay)

        lines = [
            (
                f"Fall: {'ALERT' if states['fall_alert'] else ('WATCH' if states['fall_watch'] else 'NORMAL')} | "
                f"hold={fall.horizontal_seconds:.1f}s",
                self.overlay_colors["fall_alert"]
                if states["fall_alert"]
                else self.overlay_colors["fall_watch"]
                if states["fall_watch"]
                else self.overlay_colors["safe"],
            ),
            (
                f"Inactive: {'ALERT' if states['inactive_alert'] else ('WATCH' if states['inactive_watch'] else 'NO PERSON')} | "
                f"no_motion={inactive.inactive_seconds:.1f}s",
                self.overlay_colors["inactive_alert"]
                if states["inactive_alert"]
                else self.overlay_colors["inactive_watch"]
                if states["inactive_watch"]
                else self.overlay_colors["safe"],
            ),
            (
                f"Violence: {'ALERT' if states['violence_alert'] else ('WATCH' if states['violence_watch'] else 'NORMAL')} | "
                f"persons={violence.num_persons}",
                self.overlay_colors["violence_alert"]
                if states["violence_alert"]
                else self.overlay_colors["violence_watch"]
                if states["violence_watch"]
                else self.overlay_colors["safe"],
            ),
        ]

        for line, color in lines:
            cv2 = self._get_cv2()
            cv2.putText(overlay, line, (25, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += 32

        alerts = []
        if states["fall_alert"]:
            alerts.append(("FALL / FAINTING SUSPECTED", self.overlay_colors["fall_alert"]))
        if states["inactive_alert"]:
            alerts.append(("NO RESPONSE SUSPECTED", self.overlay_colors["inactive_alert"]))
        if states["violence_alert"]:
            alerts.append(("VIOLENCE SUSPECTED", self.overlay_colors["violence_alert"]))

        banner_y = 215
        for alert, color in alerts:
            cv2 = self._get_cv2()
            cv2.rectangle(overlay, (18, banner_y - 28), (650, banner_y + 10), color, -1)
            cv2.putText(
                overlay,
                alert,
                (28, banner_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.95,
                self.overlay_colors["text"],
                2,
            )
            banner_y += 50

    def _draw_status_panel(self, overlay: np.ndarray) -> int:
        cv2 = self._get_cv2()
        cv2.rectangle(overlay, (10, 10), (980, 170), self.overlay_colors["panel"], -1)
        cv2.rectangle(overlay, (10, 10), (980, 170), (90, 90, 90), 2)
        return 40

    def _log_new_alerts(
        self,
        *,
        fall: FallDecision,
        inactive: InactiveDecision,
        violence: ViolenceDecision,
        states: dict[str, bool],
        timestamp_sec: float,
    ) -> None:
        current = {
            "fall": states["fall_alert"],
            "inactive": states["inactive_alert"],
            "violence": states["violence_alert"],
        }

        if current["fall"] and not self.last_alert_state["fall"]:
            self.event_logger.log("fall", fall, "낙상/기절 의심 이벤트가 새로 감지되었습니다.", timestamp_sec)

        if current["inactive"] and not self.last_alert_state["inactive"]:
            self.event_logger.log("inactive", inactive, "무응답 의심 이벤트가 새로 감지되었습니다.", timestamp_sec)

        if current["violence"] and not self.last_alert_state["violence"]:
            self.event_logger.log("violence", violence, "폭행 의심 이벤트가 새로 감지되었습니다.", timestamp_sec)

        self.last_alert_state = current

    def _event_metadata(self, states: dict[str, bool]) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        if states["fall_alert"]:
            events.append({"event_type": "fall", "message": "FALL / FAINTING SUSPECTED"})
        if states["inactive_alert"]:
            events.append({"event_type": "inactive", "message": "NO RESPONSE SUSPECTED"})
        if states["violence_alert"]:
            events.append({"event_type": "violence", "message": "VIOLENCE SUSPECTED"})
        return events
