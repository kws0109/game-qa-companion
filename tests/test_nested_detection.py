import cv2
import numpy as np

from companion.vision.elements import detect_boxes


def _png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_button_inside_panel_survives():
    """패널(테두리)과 그 안의 버튼 — 포함 관계는 중복이 아니므로 둘 다 검출돼야 한다."""
    img = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (300, 200), (255, 255, 255), 3)   # 패널 테두리
    cv2.rectangle(img, (80, 80), (140, 120), (200, 200, 200), -1)  # 내부 버튼
    boxes = detect_boxes(_png(img))
    assert len(boxes) == 2
    small = min(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    assert abs(small[0] - 80) <= 2 and abs(small[1] - 80) <= 2


def test_bbox_tightened_to_edges():
    """dilate로 부푼 박스가 원시 엣지 기준으로 조여져 ±2px 안에 들어와야 한다."""
    img = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.rectangle(img, (100, 100), (220, 180), (255, 255, 255), -1)
    boxes = detect_boxes(_png(img))
    assert len(boxes) == 1
    l, t, r, b = boxes[0]
    assert abs(l - 100) <= 2 and abs(t - 100) <= 2
    assert abs(r - 221) <= 2 and abs(b - 181) <= 2


def test_near_identical_boxes_still_deduped():
    """거의 같은 크기로 포개진 박스(이중 테두리)는 여전히 하나로 합쳐져야 한다."""
    img = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (200, 150), (255, 255, 255), 2)
    cv2.rectangle(img, (53, 53), (197, 147), (220, 220, 220), 2)  # 안쪽 이중 테두리
    boxes = detect_boxes(_png(img))
    assert len(boxes) == 1
