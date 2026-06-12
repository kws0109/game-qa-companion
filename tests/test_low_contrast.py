import cv2
import numpy as np

from companion.vision.elements import detect_boxes


def _low_contrast_frame() -> bytes:
    """배경(회색 100) 위에 거의 같은 색(106)의 패널 — 표준 Canny가 놓치는 저대비 UI."""
    img = np.full((300, 500, 3), 100, dtype=np.uint8)
    cv2.rectangle(img, (80, 60), (240, 160), (106, 106, 106), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_standard_edges_miss_low_contrast_panel():
    boxes = detect_boxes(_low_contrast_frame(), enhance_contrast=False)
    assert not any(abs(b[0] - 80) <= 5 and abs(b[1] - 60) <= 5 for b in boxes)


def test_clahe_recovers_low_contrast_panel():
    boxes = detect_boxes(_low_contrast_frame(), enhance_contrast=True)
    assert any(abs(b[0] - 80) <= 5 and abs(b[1] - 60) <= 5 for b in boxes)
