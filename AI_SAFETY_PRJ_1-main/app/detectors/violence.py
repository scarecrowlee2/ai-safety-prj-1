from __future__ import annotations

from dataclasses import dataclass

from app.schemas import EventMetrics


@dataclass(slots=True)
class ViolenceDecision:
    num_persons: int = 0
    max_velocity: float = 0.0
    suspicious_frames: int = 0


class ViolenceDetector:
    """
    PRD와 첨부 설계상 FA-003 스캐폴드.
    MVP 기본 범위에서는 실행하지 않으며, 향후 다중 인원 + 빠른 관절 이동 규칙으로 확장하기 위한 자리다.
    """

    # 이 메서드는 프레임에서 사람의 핵심 좌표 정보를 추출합니다.
    def extract_keypoints(self, frame) -> dict:
        return {}

    # 이 메서드는 현재 클래스의 핵심 동작을 수행합니다.
    def count_persons(self, frame) -> int:
        return 0

    # 이 메서드는 입력 데이터를 바탕으로 계산 결과를 반환합니다.
    def calculate_velocity(self, keypoints: dict) -> float:
        return 0.0

    # 이 메서드는 현재 클래스의 핵심 동작을 수행합니다.
    def is_violent(self, num_persons: int, velocity: float) -> bool:
        return num_persons >= 2 and velocity > 0.0

    # 이 메서드는 조건 충족 여부를 검사합니다.
    def check_consecutive_frames(self, suspicious: bool) -> int:
        return 1 if suspicious else 0

    # 이 메서드는 감지 결과를 이벤트 메트릭 형태로 정리합니다.
    def build_metrics(self) -> EventMetrics:
        return EventMetrics(notes={"status": "scaffold_only"})
