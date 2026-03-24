from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
import cv2

from app.core.video import WebcamReader
from app.detectors.adapters import run_fall_detector, run_inactive_detector
from app.detectors.contracts import DetectorInput
from app.detectors.fall import FallDecision, FallDetector
from app.detectors.inactive import InactiveDetector
from app.detectors.violence import ViolenceDetector
from app.storage.event_logger import EventLogger


app = FastAPI(title="Realtime Safety Stream", version="1.1.0")


# 이 메서드는 실시간 스트림에 사용할 감지기, 색상, 이벤트 로거를 준비합니다.
class RealtimeSafetyPipeline:
    def __init__(self):
        self.fall_detector = FallDetector()
        self.inactive_detector = InactiveDetector()
        self.violence_detector = ViolenceDetector(
            motion_threshold=0.025,
            pair_distance_threshold=220.0,
            hold_seconds=2.0,
        )
        self.event_logger = EventLogger("data/realtime_events.jsonl")
        self.last_alert_state = {"fall": False, "inactive": False, "violence": False}
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

    # 이 메서드는 경고 상태가 새로 켜진 순간만 골라 로그 파일에 저장합니다.
    def _log_new_alerts(self, fall: FallDecision, inactive, violence, fall_detected: bool, inactive_detected: bool, timestamp_sec: float):
        current = {
            "fall": bool(fall_detected),
            "inactive": bool(inactive_detected),
            "violence": bool(violence.should_alert),
        }

        if current["fall"] and not self.last_alert_state["fall"]:
            self.event_logger.log(
                "fall",
                fall,
                "낙상/기절 의심 이벤트가 새로 감지되었습니다.",
                timestamp_sec,
            )

        if current["inactive"] and not self.last_alert_state["inactive"]:
            self.event_logger.log(
                "inactive",
                inactive,
                "무응답 의심 이벤트가 새로 감지되었습니다.",
                timestamp_sec,
            )

        if current["violence"] and not self.last_alert_state["violence"]:
            self.event_logger.log(
                "violence",
                violence,
                "폭행 의심 이벤트가 새로 감지되었습니다.",
                timestamp_sec,
            )

        self.last_alert_state = current

    # 이 메서드는 상태 패널 배경을 그리고 상단 정보 표시에 사용할 y 좌표를 반환합니다.
    def _draw_status_panel(self, overlay):
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
        return text_x, text_y, line_height

    # 이 메서드는 각 감지기 결과를 더 선명한 색상 박스와 텍스트로 화면에 표시합니다.
    def process(self, frame, timestamp_sec: float):
        overlay = frame.copy()

        detector_input = DetectorInput(frame=frame, timestamp_sec=timestamp_sec)
        fall_result = run_fall_detector(self.fall_detector, detector_input)
        inactive_result = run_inactive_detector(self.inactive_detector, detector_input)
        fall = fall_result.raw_decision
        inactive = inactive_result.raw_decision
        violence = self.violence_detector.evaluate(frame, timestamp_sec)

        self._log_new_alerts(fall, inactive, violence, fall_result.detected, inactive_result.detected, timestamp_sec)

        text_x, y, line_height = self._draw_status_panel(overlay)

        lines = [
    (
        f"Fall: {'ALERT' if fall_result.detected else ('WATCH' if fall.is_candidate else 'NORMAL')} | "
        f"hold={fall.horizontal_seconds:.1f}s",
        self.overlay_colors["fall_alert"] if fall_result.detected else self.overlay_colors["fall_watch"] if fall.is_candidate else self.overlay_colors["safe"],
    ),
    (
        f"Inactive: {'ALERT' if inactive_result.detected else ('WATCH' if inactive.person_present else 'NO PERSON')} | "
        f"no_motion={inactive.inactive_seconds:.1f}s",
        self.overlay_colors["inactive_alert"] if inactive_result.detected else self.overlay_colors["inactive_watch"] if inactive.person_present else self.overlay_colors["safe"],
    ),
    (
        f"Violence: {'ALERT' if violence.should_alert else ('WATCH' if violence.num_persons >= 2 else 'NORMAL')} | "
        f"persons={violence.num_persons}",
        self.overlay_colors["violence_alert"] if violence.should_alert else self.overlay_colors["violence_watch"] if violence.num_persons >= 2 else self.overlay_colors["safe"],
    ),
]

        for line, color in lines:
            cv2.putText(overlay, line, (text_x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += line_height

        if inactive.bbox is not None:
            x, y1, w, h = inactive.bbox
            box_color = self.overlay_colors["inactive_alert"] if inactive.should_alert else self.overlay_colors["inactive_watch"]
            box_thickness = 4 if inactive.should_alert else 2
            cv2.rectangle(overlay, (x, y1), (x + w, y1 + h), box_color, box_thickness)
            cv2.putText(
                overlay,
                "NO RESPONSE ALERT" if inactive.should_alert else "INACTIVE WATCH",
                (x, min(frame.shape[0] - 10, y1 + h + 25)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                box_color,
                2,
            )

        for i, (x, y1, w, h) in enumerate(violence.boxes):
            box_color = self.overlay_colors["violence_alert"] if violence.should_alert else self.overlay_colors["violence_watch"]
            box_thickness = 4 if violence.should_alert else 2
            cv2.rectangle(overlay, (x, y1), (x + w, y1 + h), box_color, box_thickness)
            cv2.putText(
                overlay,
                f"P{i+1}",
                (x, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                box_color,
                2,
            )

        alerts = []
        if fall_result.detected:
            alerts.append(("FALL / FAINTING SUSPECTED", self.overlay_colors["fall_alert"]))
        if inactive_result.detected:
            alerts.append(("NO RESPONSE SUSPECTED", self.overlay_colors["inactive_alert"]))
        if violence.should_alert:
            alerts.append(("VIOLENCE SUSPECTED", self.overlay_colors["violence_alert"]))

        banner_y = 215
        for alert, color in alerts:
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

        states = {
            "fall": fall,
            "inactive": inactive,
            "violence": violence,
        }
        return overlay, states


pipeline = RealtimeSafetyPipeline()


# 이 함수는 웹캠 프레임을 읽고 실시간 감지 결과를 덧그린 뒤 MJPEG 형식으로 전송합니다.
def generate_frames(camera_index: int = 0):
    reader = WebcamReader(camera_index)
    try:
        for frame in reader.read():
            img = frame.image
            output, _states = pipeline.process(img, frame.timestamp_sec)

            ret, buffer = cv2.imencode(".jpg", output)
            if not ret:
                continue
            frame_bytes = buffer.tobytes()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
    finally:
        reader.release()


# 이 함수는 스트리밍 영상을 바로 볼 수 있는 간단한 테스트 페이지를 반환합니다.
@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <html>
      <head><title>AI Safety Realtime Monitor</title></head>
      <body style="font-family: Arial; background:#111; color:#eee; text-align:center;">
        <h1>AI Safety Realtime Monitor</h1>
        <p>낙상/무응답/폭행 의심 오버레이와 색상 경고가 함께 표시됩니다.</p>
        <p>로그 파일: <code>data/realtime_events.jsonl</code></p>
        <img src="/video" style="max-width:95vw; border:2px solid #444;" />
      </body>
    </html>
    """


# 이 함수는 브라우저로 실시간 영상 스트림을 반환하는 API 엔드포인트입니다.
@app.get("/video")
def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
