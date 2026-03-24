import cv2


class VideoFrame:
    # 이 메서드는 프레임 이미지와 시간을 함께 담는 객체를 준비합니다.
    def __init__(self, image, timestamp_sec=0.0):
        self.image = image
        self.timestamp_sec = timestamp_sec


class WebcamReader:
    # 이 메서드는 웹캠 입력 장치를 열고 기본 설정을 준비합니다.
    def __init__(self, src=0, width=1280, height=720):
        self.src = src
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(src)
        if not self.cap.isOpened():
            raise RuntimeError(f"웹캠을 열 수 없습니다. camera index={src}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 0.0
        if self.fps <= 0:
            self.fps = 30.0
        self.frame_index = 0

    # 이 메서드는 웹캠에서 프레임을 계속 읽어 VideoFrame 형태로 반환합니다.
    def read(self):
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            timestamp_sec = self.frame_index / max(self.fps, 1.0)
            self.frame_index += 1
            yield VideoFrame(frame, timestamp_sec=timestamp_sec)

    # 이 메서드는 사용이 끝난 웹캠 장치를 안전하게 해제합니다.
    def release(self):
        if self.cap:
            self.cap.release()
