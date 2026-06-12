import cv2
import numpy as np

from companion.vision.elements import detect_elements, stability_mask_from_pngs


def _png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_stability_mask_from_pngs_burst():
    """버스트 프레임 묶음 — 고정 HUD는 안정(255), 움직이는 사각형은 가변(0)."""
    pngs = []
    for i in range(8):
        img = np.full((300, 500, 3), 90, dtype=np.uint8)
        x = 150 + i * 30  # 결정적 수평 이동 — (175,300) 픽셀을 절반의 프레임이 밟음
        cv2.rectangle(img, (x, 140), (x + 90, 210), (250, 250, 250), -1)
        cv2.rectangle(img, (40, 30), (160, 80), (240, 240, 240), -1)  # 고정 HUD
        pngs.append(_png(img))
    mask = stability_mask_from_pngs(pngs, std_threshold=30.0)
    assert mask[55, 100] == 255  # HUD
    assert mask[175, 300] == 0   # 월드 이동 경로


class FakeOcr:
    """(60,50)-(140,90) 박스 안에 텍스트 1건을 돌려주는 가짜 엔진."""

    def read_items(self, png):
        return [("전투", (70, 60, 120, 80))]


def _frame_three_boxes() -> bytes:
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.rectangle(img, (60, 50), (140, 90), (255, 255, 255), -1)    # 텍스트 포함 — 유지
    cv2.rectangle(img, (250, 180), (340, 230), (200, 200, 200), -1)  # 중앙·텍스트 없음 — 제거
    cv2.rectangle(img, (560, 10), (595, 45), (180, 180, 180), -1)    # 가장자리 아이콘 — 유지
    return _png(img)


def test_text_anchor_drops_center_textless_box():
    els = detect_elements(_frame_three_boxes(), ocr_engine=FakeOcr(), text_anchor=True)
    boxes = [e for e in els if e.kind == "box"]
    assert len(boxes) == 2
    labels_or_pos = {(e.label, e.bbox[0] >= 550) for e in boxes}
    assert ("전투", False) in labels_or_pos      # 텍스트 앵커로 생존
    assert ("", True) in labels_or_pos           # 가장자리 예외로 생존


def test_text_anchor_off_keeps_all():
    els = detect_elements(_frame_three_boxes(), ocr_engine=FakeOcr(), text_anchor=False)
    assert len([e for e in els if e.kind == "box"]) == 3
