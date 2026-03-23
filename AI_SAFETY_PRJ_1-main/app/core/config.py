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

    spring_boot_event_url: str = os.getenv("SPRING_BOOT_EVENT_URL", "").strip()
    spring_boot_sleep_setting_url: str = os.getenv("SPRING_BOOT_SLEEP_SETTING_URL", "").strip()
    http_timeout_seconds: float = float(os.getenv("HTTP_TIMEOUT_SECONDS", "5.0"))
    retry_max_attempts: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    retry_backoff_seconds: float = float(os.getenv("RETRY_BACKOFF_SECONDS", "1.5"))

    sample_fps: float = float(os.getenv("SAMPLE_FPS", "5.0"))

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

    inactive_seconds: float = float(os.getenv("INACTIVE_SECONDS", "30.0"))
    motion_threshold: float = float(os.getenv("MOTION_THRESHOLD", "0.002"))
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


settings = Settings()
settings.ensure_directories()
