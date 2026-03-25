from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Smart Safety MVP - Python Detector")
    app_env: str = os.getenv("APP_ENV", "dev")
    app_timezone: str = os.getenv("APP_TIMEZONE", "Asia/Seoul")

    data_dir: Path = Path(os.getenv("DATA_DIR", "./data")).expanduser()
    models_dir: Path = Path(os.getenv("MODELS_DIR", "./models")).expanduser()
    snapshot_dir: Path = Path(os.getenv("SNAPSHOT_DIR", "./data/snapshots")).expanduser()
    sqlite_path: Path = Path(os.getenv("SQLITE_PATH", "./data/events.db")).expanduser()
    outbox_jsonl: Path = Path(os.getenv("OUTBOX_JSONL", "./data/outbox/events.jsonl")).expanduser()
    temp_upload_dir: Path = Path(os.getenv("TEMP_UPLOAD_DIR", "./data/uploads")).expanduser()
    upload_write_chunk_size: int = int(os.getenv("UPLOAD_WRITE_CHUNK_SIZE", str(1024 * 1024)))
    keep_temp_upload_files: bool = os.getenv("KEEP_TEMP_UPLOAD_FILES", "false").lower() == "true"

    spring_boot_event_url: str = os.getenv("SPRING_BOOT_EVENT_URL", "").strip()
    spring_boot_sleep_setting_url: str = os.getenv("SPRING_BOOT_SLEEP_SETTING_URL", "").strip()
    http_timeout_seconds: float = float(os.getenv("HTTP_TIMEOUT_SECONDS", "5.0"))
    retry_max_attempts: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    retry_backoff_seconds: float = float(os.getenv("RETRY_BACKOFF_SECONDS", "1.5"))

    sample_fps: float = float(os.getenv("SAMPLE_FPS", "5.0"))
    realtime_event_log_path: Path = Path(os.getenv("REALTIME_EVENT_LOG_PATH", "./data/realtime_events.jsonl")).expanduser()
    realtime_recent_event_limit: int = int(os.getenv("REALTIME_RECENT_EVENT_LIMIT", "6"))
    realtime_recent_event_max_limit: int = int(os.getenv("REALTIME_RECENT_EVENT_MAX_LIMIT", "20"))
    realtime_mjpeg_boundary: str = os.getenv("REALTIME_MJPEG_BOUNDARY", "frame").strip() or "frame"
    realtime_webcam_source: str = os.getenv("REALTIME_WEBCAM_SOURCE", "0").strip()
    realtime_webcam_width: int = int(os.getenv("REALTIME_WEBCAM_WIDTH", "960"))
    realtime_webcam_height: int = int(os.getenv("REALTIME_WEBCAM_HEIGHT", "540"))
    realtime_webcam_fps: float = float(os.getenv("REALTIME_WEBCAM_FPS", "15.0"))
    realtime_analysis_fps: float = float(os.getenv("REALTIME_ANALYSIS_FPS", "5.0"))
    realtime_overlay_stale_threshold_ms: int = int(os.getenv("REALTIME_OVERLAY_STALE_THRESHOLD_MS", "3000"))
    realtime_sse_keepalive_interval_sec: float = float(os.getenv("REALTIME_SSE_KEEPALIVE_INTERVAL_SEC", "15.0"))
    realtime_webcam_backend: int | None = (
        int(os.getenv("REALTIME_WEBCAM_BACKEND", "").strip())
        if os.getenv("REALTIME_WEBCAM_BACKEND", "").strip()
        else None
    )
    realtime_violence_motion_threshold: float = float(os.getenv("REALTIME_VIOLENCE_MOTION_THRESHOLD", "0.025"))
    realtime_violence_pair_distance_threshold: float = float(os.getenv("REALTIME_VIOLENCE_PAIR_DISTANCE_THRESHOLD", "220.0"))
    realtime_violence_hold_seconds: float = float(os.getenv("REALTIME_VIOLENCE_HOLD_SECONDS", "2.0"))
    realtime_notify_enabled: bool = os.getenv("REALTIME_NOTIFY_ENABLED", "false").lower() == "true"
    # Outbound notifier MVP default: fall/inactive only (violence stays internal realtime signal).
    realtime_notify_event_types: str = os.getenv("REALTIME_NOTIFY_EVENT_TYPES", "fall,inactive")
    realtime_notify_resident_id: int = int(os.getenv("REALTIME_NOTIFY_RESIDENT_ID", "1"))

    fall_enabled: bool = os.getenv("FALL_ENABLED", "true").lower() == "true"
    fall_pose_task_model_path: Path = Path(
        os.getenv("FALL_POSE_TASK_MODEL_PATH", "./models/pose_landmarker.task")
    ).expanduser()
    fall_hold_seconds: float = float(os.getenv("FALL_HOLD_SECONDS", "5.0"))
    fall_angle_threshold_deg: float = float(os.getenv("FALL_ANGLE_THRESHOLD_DEG", "60.0"))
    fall_min_visibility: float = float(os.getenv("FALL_MIN_VISIBILITY", "0.4"))
    fall_min_pose_detection_confidence: float = float(os.getenv("FALL_MIN_POSE_DETECTION_CONFIDENCE", "0.5"))
    fall_min_pose_presence_confidence: float = float(os.getenv("FALL_MIN_POSE_PRESENCE_CONFIDENCE", "0.5"))
    fall_min_tracking_confidence: float = float(os.getenv("FALL_MIN_TRACKING_CONFIDENCE", "0.5"))
    fall_enable_hog_fallback: bool = os.getenv("FALL_ENABLE_HOG_FALLBACK", "true").lower() == "true"
    fall_hog_aspect_ratio_threshold: float = float(os.getenv("FALL_HOG_ASPECT_RATIO_THRESHOLD", "1.15"))

    inactive_seconds: float = float(os.getenv("INACTIVE_SECONDS", "30.0"))
    motion_threshold: float = float(os.getenv("MOTION_THRESHOLD", "0.002"))
    # 운영 권장값: true (person gate가 준비되지 않으면 inactive detector가 degraded/error가 될 수 있음)
    # 개발/테스트: optional dependency(ultralytics/YOLO 가중치) 부담을 줄이기 위해 false 가능
    enable_yolo_person_gate: bool = os.getenv("ENABLE_YOLO_PERSON_GATE", "false").lower() == "true"
    yolo_model: str = os.getenv("YOLO_MODEL", "yolov8n.pt")

    no_event_cooldown_seconds: float = float(os.getenv("NO_EVENT_COOLDOWN_SECONDS", "20.0"))
    snapshot_expire_days: int = int(os.getenv("SNAPSHOT_EXPIRE_DAYS", "7"))

    # 이 메서드는 현재 클래스의 핵심 동작을 수행합니다.
    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.temp_upload_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.realtime_event_log_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
