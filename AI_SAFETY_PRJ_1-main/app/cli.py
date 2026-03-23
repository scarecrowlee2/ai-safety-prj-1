from __future__ import annotations

import argparse
import json

from app.core.analyzer import VideoAnalyzer
from app.notifier import EventNotifier
from app.storage.event_store import EventStore


# 이 함수는 CLI 실행에 필요한 인자 파서를 구성합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI 스마트 생활안전 서비스 MVP 비디오 분석기")
    parser.add_argument("--resident-id", type=int, required=True, help="보호 대상자 ID")
    parser.add_argument("--video", type=str, required=True, help="분석할 비디오 파일 경로")
    parser.add_argument("--notify", action="store_true", help="분석 후 Spring Boot로 이벤트 전송 시도")
    return parser


# 이 함수는 프로그램의 전체 실행 흐름을 시작합니다.
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    analyzer = VideoAnalyzer()
    result = analyzer.analyze_video(resident_id=args.resident_id, video_path=args.video)
    payload = result.model_dump(mode="json")

    if args.notify:
        notifier = EventNotifier(EventStore())
        payload["notification_results"] = [
            notifier.send_event(event).model_dump(mode="json") for event in result.events
        ]

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
