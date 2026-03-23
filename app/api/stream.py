from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from string import Template

import cv2
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.core.video import WebcamReader
from app.detectors.fall import FallDetector
from app.detectors.inactive import InactiveDetector
from app.detectors.violence import ViolenceDetector
from app.storage.event_logger import EventLogger


app = FastAPI(title="Realtime Safety Stream", version="1.2.0")

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
REALTIME_TEMPLATE_PATH = TEMPLATES_DIR / "realtime_monitor.html"
EVENT_LOG_PATH = Path("data/realtime_events.jsonl")
RECENT_EVENT_LIMIT = 6

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# 이 메서드는 실시간 스트림에 사용할 감지기, 색상, 이벤트 로거를 준비합니다.
class RealtimeSafetyPipeline:
    def __init__(self):
        self.fall_detector = FallDetector(hold_seconds=3.0, aspect_ratio_threshold=1.15)
        self.inactive_detector = InactiveDetector(inactive_seconds=20.0, motion_threshold=0.002)
        self.violence_detector = ViolenceDetector(
            motion_threshold=0.025,
            pair_distance_threshold=220.0,
            hold_seconds=2.0,
        )
        self.event_logger = EventLogger(str(EVENT_LOG_PATH))
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
    def _log_new_alerts(self, fall, inactive, violence, timestamp_sec: float):
        current = {
            "fall": bool(fall.should_alert),
            "inactive": bool(inactive.should_alert),
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

    # 이 메서드는 화면 내부 상태 패널 배경을 그리고 상단 정보 표시에 사용할 y 좌표를 반환합니다.
    def _draw_status_panel(self, overlay):
        h, w = overlay.shape[:2]

        left = 10
        top = 10
        right = w - 10       # 화면 오른쪽 끝에서 10px 안쪽
        bottom = 125         # 패널 높이 줄임

        cv2.rectangle(overlay, (left, top), (right, bottom), self.overlay_colors["panel"], -1)
        cv2.rectangle(overlay, (left, top), (right, bottom), (90, 90, 90), 2)
        return 38

    # 이 메서드는 각 감지기 결과를 더 선명한 색상 박스와 텍스트로 화면에 표시합니다.
    def process(self, frame, timestamp_sec: float):
        overlay = frame.copy()

        fall = self.fall_detector.evaluate(frame, timestamp_sec)
        inactive = self.inactive_detector.evaluate(frame, timestamp_sec)
        violence = self.violence_detector.evaluate(frame, timestamp_sec)

        self._log_new_alerts(fall, inactive, violence, timestamp_sec)

        y = self._draw_status_panel(overlay)

        lines = [
        (
            f"Fall: {'ALERT' if fall.should_alert else ('WATCH' if fall.is_candidate else 'NORMAL')} | "
            f"hold={fall.horizontal_seconds:.1f}s",
            self.overlay_colors["fall_alert"] if fall.should_alert else self.overlay_colors["fall_watch"] if fall.is_candidate else self.overlay_colors["safe"],
        ),
        (
            f"Inactive: {'ALERT' if inactive.should_alert else ('WATCH' if inactive.person_present else 'NO PERSON')} | "
            f"no_motion={inactive.inactive_seconds:.1f}s",
            self.overlay_colors["inactive_alert"] if inactive.should_alert else self.overlay_colors["inactive_watch"] if inactive.person_present else self.overlay_colors["safe"],
        ),
        (
            f"Violence: {'ALERT' if violence.should_alert else ('WATCH' if violence.num_persons >= 2 else 'NORMAL')} | "
            f"persons={violence.num_persons}",
            self.overlay_colors["violence_alert"] if violence.should_alert else self.overlay_colors["violence_watch"] if violence.num_persons >= 2 else self.overlay_colors["safe"],
        ),
]

        for line, color in lines:
            cv2.putText(overlay, line, (25, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            y += 32

        if fall.bbox is not None:
            x, y1, w, h = fall.bbox
            box_color = self.overlay_colors["fall_alert"] if fall.should_alert else self.overlay_colors["fall_watch"]
            box_thickness = 4 if fall.should_alert else 2
            cv2.rectangle(overlay, (x, y1), (x + w, y1 + h), box_color, box_thickness)
            cv2.putText(
                overlay,
                "FALL ALERT" if fall.should_alert else "FALL WATCH",
                (x, max(30, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                box_color,
                2,
            )

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
        if fall.should_alert:
            alerts.append(("FALL / FAINTING SUSPECTED", self.overlay_colors["fall_alert"]))
        if inactive.should_alert:
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


# 이 함수는 최근 JSONL 이벤트 몇 건을 시간순으로 반환합니다.
def _load_recent_events(limit: int = RECENT_EVENT_LIMIT) -> list[dict]:
    if not EVENT_LOG_PATH.exists():
        return []

    recent_lines = deque(maxlen=limit)
    with EVENT_LOG_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                recent_lines.append(stripped)

    events = []
    for raw_line in reversed(recent_lines):
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        events.append(
            {
                "event_type": record.get("event_type", "unknown"),
                "message": record.get("message", "이벤트 정보가 없습니다."),
                "logged_at": record.get("logged_at"),
                "stream_timestamp_sec": record.get("stream_timestamp_sec"),
            }
        )
    return events


# 이 함수는 운영 대시보드 형태의 실시간 모니터링 페이지를 렌더링합니다.
@app.get("/", response_class=HTMLResponse)
def index():
    template = Template(REALTIME_TEMPLATE_PATH.read_text(encoding="utf-8"))
    html = template.safe_substitute(
        service_title="AI Safety Realtime Monitor",
        service_description="낙상·무응답·폭행 이상 징후를 실시간으로 감시하는 운영 대시보드입니다.",
        log_path=str(EVENT_LOG_PATH),
        monitoring_state="LIVE",
        recent_event_count=RECENT_EVENT_LIMIT,
        css_path="/static/css/realtime_monitor.css",
        js_path="/static/js/realtime_monitor.js",
    )
    return HTMLResponse(html)


# 이 함수는 브라우저에서 최근 이벤트 목록을 읽을 수 있게 JSON으로 제공합니다.
@app.get("/api/recent-events")
def recent_events(limit: int = RECENT_EVENT_LIMIT):
    limit = max(1, min(limit, 20))
    return JSONResponse({"events": _load_recent_events(limit=limit), "log_path": str(EVENT_LOG_PATH)})


# 이 함수는 브라우저로 실시간 영상 스트림을 반환하는 API 엔드포인트입니다.
@app.get("/video")
def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
