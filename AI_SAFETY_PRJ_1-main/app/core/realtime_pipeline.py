from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.detectors.adapters import run_fall_detector, run_inactive_detector, run_violence_detector
from app.detectors.contracts import DetectorInput, OverlayAnnotation
from app.detectors.fall import FallDecision, FallDetector
from app.detectors.inactive import InactiveDecision, InactiveDetector
from app.detectors.violence import ViolenceDecision, ViolenceDetector
from app.core.config import settings
from app.storage.event_logger import EventLogger


BOX_COORD_SYSTEM_NORMALIZED_XYXY = "normalized_xyxy"


@dataclass(slots=True)
class RealtimePipelineResult:
    """Processed frame plus structured metadata for realtime stream consumers."""

    frame: np.ndarray
    metadata: dict[str, Any]


class RealtimePipeline:
    """Realtime frame-processing coordinator used by streaming routes."""

    def __init__(
        self,
        event_log_path: str | None = None,
        event_logger: EventLogger | None = None,
    ) -> None:
        self.fall_detector = FallDetector()
        self.inactive_detector = InactiveDetector()
        self.violence_detector = ViolenceDetector(
            motion_threshold=settings.realtime_violence_motion_threshold,
            pair_distance_threshold=settings.realtime_violence_pair_distance_threshold,
            hold_seconds=settings.realtime_violence_hold_seconds,
        )
        resolved_log_path = event_log_path or str(settings.realtime_event_log_path)
        self.event_logger = event_logger or EventLogger(resolved_log_path)

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
            try:
                import cv2
            except Exception:
                self._cv2 = False
            else:
                self._cv2 = cv2
        return self._cv2 if self._cv2 is not False else None

    def process_frame(self, frame: np.ndarray, timestamp_sec: float) -> RealtimePipelineResult:
        """Backward-compatible wrapper that analyzes then renders server-side overlays."""

        analysis = self.analyze_frame(frame=frame, timestamp_sec=timestamp_sec)
        overlay = self.render_overlay(frame=frame, overlay_payload=analysis["overlay_payload"])
        return RealtimePipelineResult(frame=overlay, metadata=analysis["metadata"])

    def analyze_frame(
        self,
        *,
        frame: np.ndarray,
        timestamp_sec: float,
        frame_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Run detectors/event logging and return structured overlay payload + metadata.

        This method never draws on the frame.

        Example `overlay_payload`:
        {
          "frame_id": "cam1-1203",
          "timestamp_sec": 1712345678.12,
          "source_size": {"width": 1280, "height": 720},
          "box_coord_system": "normalized_xyxy",
          "states": {"fall_alert": false, "fall_watch": true, ...},
          "objects": [{"label": "pair-risk", "type": "violence", "style": {...}, "box": {...}}],
          "banners": [{"text": "VIOLENCE SUSPECTED", "level": "violence_alert"}],
          "status_lines": [{"text": "Fall: WATCH | hold=1.2s", "color_bgr": [0, 200, 255]}]
        }
        """

        frame_height, frame_width = frame.shape[:2]

        detector_input = DetectorInput(frame=frame, timestamp_sec=timestamp_sec)
        fall_result = run_fall_detector(self.fall_detector, detector_input)
        inactive_result = run_inactive_detector(self.inactive_detector, detector_input)
        violence_result = run_violence_detector(self.violence_detector, detector_input)

        fall = fall_result.raw_decision
        inactive = inactive_result.raw_decision
        violence = violence_result.raw_decision

        states = self._build_state_flags(
            fall=fall,
            inactive=inactive,
            violence=violence,
            fall_detected=fall_result.detected,
            inactive_detected=inactive_result.detected,
            violence_detected=violence_result.detected,
        )
        new_logged_events = self._log_new_alerts(
            fall=fall,
            inactive=inactive,
            violence=violence,
            states=states,
            timestamp_sec=timestamp_sec,
        )

        overlay_payload = self._build_overlay_payload(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            frame_width=frame_width,
            frame_height=frame_height,
            states=states,
            fall=fall,
            inactive=inactive,
            violence=violence,
            violence_overlays=violence_result.overlays,
        )

        metadata = {
            "timestamp_sec": timestamp_sec,
            "states": states,
            "events": self._event_metadata(states),
            "new_logged_events": new_logged_events,
            "overlay_payload": overlay_payload,
            "detections": {
                "fall": fall_result.to_dict(),
                "inactive": inactive_result.to_dict(),
                "violence": violence_result.to_dict(),
            },
        }
        return {"overlay_payload": overlay_payload, "metadata": metadata}

    def render_overlay(self, *, frame: np.ndarray, overlay_payload: dict[str, Any]) -> np.ndarray:
        """Draw overlay objects/banners from `overlay_payload` onto a copy of `frame`."""

        overlay = frame.copy()
        cv2 = self._get_cv2()
        if cv2 is None:
            return overlay

        states = overlay_payload.get("states", {})
        status_lines = overlay_payload.get("status_lines", [])
        objects = overlay_payload.get("objects", [])
        banners = overlay_payload.get("banners", [])
        source_size = overlay_payload.get("source_size", {})
        source_width = max(1, int(source_size.get("width", overlay.shape[1])))
        source_height = max(1, int(source_size.get("height", overlay.shape[0])))
        coord_system = overlay_payload.get("box_coord_system", BOX_COORD_SYSTEM_NORMALIZED_XYXY)

        text_x, y, line_height = self._draw_status_panel(overlay)
        for line in status_lines:
            color = tuple(line.get("color_bgr", self.overlay_colors["safe"]))
            cv2.putText(overlay, line.get("text", ""), (text_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += line_height

        for obj in objects:
            box = obj.get("box")
            if not box:
                continue
            x1, y1, x2, y2 = self._box_to_pixel_xyxy(
                box=box,
                coord_system=coord_system,
                source_width=source_width,
                source_height=source_height,
            )
            style = obj.get("style", {})
            box_color = tuple(style.get("color_bgr", self.overlay_colors["violence_watch"]))
            box_thickness = int(style.get("thickness", 2))
            cv2.rectangle(overlay, (x1, y1), (x2, y2), box_color, box_thickness)
            cv2.putText(
                overlay,
                obj.get("label", ""),
                (x1, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                box_color,
                2,
            )

        banner_y = 215
        for banner in banners:
            color = self._banner_color(level=banner.get("level", "watch"), states=states)
            cv2.rectangle(overlay, (18, banner_y - 28), (650, banner_y + 10), color, -1)
            cv2.putText(
                overlay,
                banner.get("text", ""),
                (28, banner_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.95,
                self.overlay_colors["text"],
                2,
            )
            banner_y += 50

        return overlay

    def _build_state_flags(
        self,
        *,
        fall: FallDecision,
        inactive: InactiveDecision,
        violence: ViolenceDecision,
        fall_detected: bool,
        inactive_detected: bool,
        violence_detected: bool,
    ) -> dict[str, bool]:
        fall_alert = fall_detected
        inactive_alert = inactive_detected
        violence_alert = violence_detected

        return {
            "fall_alert": fall_alert,
            "fall_watch": fall.is_candidate and not fall_alert,
            "inactive_alert": inactive_alert,
            "inactive_watch": inactive.person_present and not inactive_alert,
            "violence_alert": violence_alert,
            "violence_watch": (violence.num_persons >= 2) and not violence_alert,
        }

    def _build_overlay_payload(
        self,
        *,
        frame_id: int | str | None,
        timestamp_sec: float,
        frame_width: int,
        frame_height: int,
        states: dict[str, bool],
        fall: FallDecision,
        inactive: InactiveDecision,
        violence: ViolenceDecision,
        violence_overlays: list[OverlayAnnotation],
    ) -> dict[str, Any]:
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
        status_lines = [{"text": line, "color_bgr": list(color)} for line, color in lines]

        objects: list[dict[str, Any]] = []
        for annotation in violence_overlays:
            if annotation.box_xyxy is None:
                continue
            x1, y1, x2, y2 = annotation.box_xyxy
            box_color = annotation.color_bgr or (
                self.overlay_colors["violence_alert"] if states["violence_alert"] else self.overlay_colors["violence_watch"]
            )
            objects.append(
                {
                    "label": annotation.label,
                    "type": "violence",
                    "style": {
                        "color_bgr": list(box_color),
                        "thickness": 4 if states["violence_alert"] else 2,
                    },
                    "box": self._normalize_box_xyxy(
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        frame_width=frame_width,
                        frame_height=frame_height,
                    ),
                }
            )

        banners: list[dict[str, str]] = []
        if states["fall_alert"]:
            banners.append({"text": "FALL / FAINTING SUSPECTED", "level": "fall_alert"})
        if states["inactive_alert"]:
            banners.append({"text": "NO RESPONSE SUSPECTED", "level": "inactive_alert"})
        if states["violence_alert"]:
            banners.append({"text": "VIOLENCE SUSPECTED", "level": "violence_alert"})

        return {
            "frame_id": frame_id,
            "timestamp_sec": timestamp_sec,
            "source_size": {"width": frame_width, "height": frame_height},
            "box_coord_system": BOX_COORD_SYSTEM_NORMALIZED_XYXY,
            "states": states,
            "objects": objects,
            "banners": banners,
            "status_lines": status_lines,
        }

    def _normalize_box_xyxy(
        self,
        *,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        frame_width: int,
        frame_height: int,
    ) -> dict[str, float]:
        width = max(1, frame_width)
        height = max(1, frame_height)
        return {
            "x1": max(0.0, min(1.0, float(x1) / width)),
            "y1": max(0.0, min(1.0, float(y1) / height)),
            "x2": max(0.0, min(1.0, float(x2) / width)),
            "y2": max(0.0, min(1.0, float(y2) / height)),
        }

    def _box_to_pixel_xyxy(
        self,
        *,
        box: dict[str, Any],
        coord_system: str,
        source_width: int,
        source_height: int,
    ) -> tuple[int, int, int, int]:
        if coord_system == BOX_COORD_SYSTEM_NORMALIZED_XYXY:
            return (
                int(float(box.get("x1", 0.0)) * source_width),
                int(float(box.get("y1", 0.0)) * source_height),
                int(float(box.get("x2", 0.0)) * source_width),
                int(float(box.get("y2", 0.0)) * source_height),
            )
        return (
            int(box.get("x1", 0)),
            int(box.get("y1", 0)),
            int(box.get("x2", 0)),
            int(box.get("y2", 0)),
        )

    def _banner_color(self, *, level: str, states: dict[str, bool]) -> tuple[int, int, int]:
        if level == "fall_alert":
            return self.overlay_colors["fall_alert"]
        if level == "inactive_alert":
            return self.overlay_colors["inactive_alert"]
        if level == "violence_alert":
            return self.overlay_colors["violence_alert"]
        return self.overlay_colors["violence_alert"] if states.get("violence_alert") else self.overlay_colors["safe"]

    def _draw_status_panel(self, overlay: np.ndarray) -> tuple[int, int, int]:
        cv2 = self._get_cv2()
        if cv2 is None:
            return (25, 40, 32)

        frame_height, frame_width = overlay.shape[:2]

        panel_margin_x = 10
        panel_top_y = 10
        panel_height = 160
        panel_padding_x = 15
        panel_top_padding = 30
        line_height = 32

        panel_x1 = max(0, panel_margin_x)
        panel_x2 = frame_width - panel_margin_x - 1
        if panel_x2 <= panel_x1:
            panel_x1 = 0
            panel_x2 = max(0, frame_width - 1)

        panel_y1 = max(0, panel_top_y)
        panel_y2 = min(frame_height - 1, panel_y1 + panel_height)
        if panel_y2 <= panel_y1:
            panel_y1 = 0
            panel_y2 = max(0, frame_height - 1)

        cv2.rectangle(overlay, (panel_x1, panel_y1), (panel_x2, panel_y2), self.overlay_colors["panel"], -1)
        cv2.rectangle(overlay, (panel_x1, panel_y1), (panel_x2, panel_y2), (90, 90, 90), 2)

        text_x = max(0, min(panel_x2 - 4, panel_x1 + panel_padding_x))
        text_y = max(0, min(panel_y2 - 4, panel_y1 + panel_top_padding))
        return (text_x, text_y, line_height)

    def _log_new_alerts(
        self,
        *,
        fall: FallDecision,
        inactive: InactiveDecision,
        violence: ViolenceDecision,
        states: dict[str, bool],
        timestamp_sec: float,
    ) -> list[dict[str, Any]]:
        current = {
            "fall": states["fall_alert"],
            "inactive": states["inactive_alert"],
            "violence": states["violence_alert"],
        }
        new_logged_events: list[dict[str, Any]] = []

        if current["fall"] and not self.last_alert_state["fall"]:
            new_logged_events.append(
                self.event_logger.log("fall", fall, "낙상/기절 의심 이벤트가 새로 감지되었습니다.", timestamp_sec)
            )

        if current["inactive"] and not self.last_alert_state["inactive"]:
            new_logged_events.append(
                self.event_logger.log("inactive", inactive, "무응답 의심 이벤트가 새로 감지되었습니다.", timestamp_sec)
            )

        if current["violence"] and not self.last_alert_state["violence"]:
            new_logged_events.append(
                self.event_logger.log("violence", violence, "폭행 의심 이벤트가 새로 감지되었습니다.", timestamp_sec)
            )

        self.last_alert_state = current
        return new_logged_events

    def _event_metadata(self, states: dict[str, bool]) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        if states["fall_alert"]:
            events.append({"event_type": "fall", "message": "FALL / FAINTING SUSPECTED"})
        if states["inactive_alert"]:
            events.append({"event_type": "inactive", "message": "NO RESPONSE SUSPECTED"})
        if states["violence_alert"]:
            events.append({"event_type": "violence", "message": "VIOLENCE SUSPECTED"})
        return events
