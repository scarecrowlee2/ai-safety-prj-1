from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import cv2
import numpy as np


@dataclass(slots=True)
class VideoFrame:
    frame_index: int
    timestamp_sec: float
    image: np.ndarray


@dataclass(slots=True)
class VideoMetadata:
    fps: float
    width: int
    height: int
    frame_count: int
    duration_sec: float


class VideoReader:
    # 이 메서드는 클래스가 동작하는 데 필요한 초기 상태와 객체를 준비합니다.
    def __init__(self, video_path: str | Path, sample_fps: float) -> None:
        self.video_path = str(video_path)
        self.sample_fps = sample_fps

    # 이 메서드는 입력 소스에서 프레임 또는 데이터를 순차적으로 읽어 반환합니다.
    def read(self) -> tuple[VideoMetadata, Generator[VideoFrame, None, None]]:
        capture = cv2.VideoCapture(self.video_path)
        if not capture.isOpened():
            raise ValueError(f"비디오를 열 수 없습니다: {self.video_path}")

        source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_sec = frame_count / source_fps if source_fps > 0 else 0.0

        metadata = VideoMetadata(
            fps=source_fps,
            width=width,
            height=height,
            frame_count=frame_count,
            duration_sec=duration_sec,
        )

        stride = max(int(round(source_fps / max(self.sample_fps, 0.1))), 1)

        # 이 메서드는 현재 클래스의 핵심 동작을 수행합니다.
        def generator() -> Generator[VideoFrame, None, None]:
            frame_idx = 0
            try:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if frame_idx % stride == 0:
                        timestamp_sec = frame_idx / source_fps if source_fps > 0 else 0.0
                        yield VideoFrame(
                            frame_index=frame_idx,
                            timestamp_sec=timestamp_sec,
                            image=frame,
                        )
                    frame_idx += 1
            finally:
                capture.release()

        return metadata, generator()
