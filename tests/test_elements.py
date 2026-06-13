import json
from pathlib import Path

from companion.providers.base import FakeProvider
from companion.vision.elements import (
    detect_boxes, detect_elements, label_elements, render_overlay, save_inspection,
)


def _two_button_frame(make_png) -> bytes:
    """검은 배경 + 흰 사각 버튼 2개 (50,40)-(150,80), (200,300)-(360,360)."""
    import cv2
    import numpy as np
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 40), (150, 80), (255, 255, 255), -1)
    cv2.rectangle(img, (200, 300), (360, 360), (200, 200, 200), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_detect_boxes_finds_two_rects(make_png):
    boxes = detect_boxes(_two_button_frame(make_png))
    assert len(boxes) == 2
    # 좌상단 정렬 — 첫 박스가 (50,40) 근처
    l, t, r, b = boxes[0]
    assert abs(l - 50) <= 4 and abs(t - 40) <= 4


def test_detect_elements_assigns_ids_and_centers(make_png):
    els = detect_elements(_two_button_frame(make_png))
    assert [e.id for e in els] == [1, 2]
    assert els[0].kind == "box"
    cx, cy = els[0].center
    assert 90 <= cx <= 110 and 50 <= cy <= 70


def test_label_elements_merges_llm_roles(make_png):
    els = detect_elements(_two_button_frame(make_png))
    provider = FakeProvider(responses=[json.dumps({"elements": [
        {"id": 1, "role": "button", "name": "전투 시작"},
        {"id": 2, "role": "panel", "name": "퀘스트 창"}]})])
    labeled = label_elements(els, Path("annotated.png"), provider)
    assert labeled[0].kind == "button" and labeled[0].label == "전투 시작"
    assert labeled[1].kind == "panel"
    # 좌표는 LLM이 못 건드림
    assert labeled[0].bbox == els[0].bbox


def test_save_inspection_writes_catalog(tmp_path: Path, make_png):
    png = _two_button_frame(make_png)
    els = detect_elements(png)
    out = save_inspection(tmp_path / "insp", png, els)
    assert (out / "annotated.png").exists()
    assert (out / "source.png").exists()
    data = json.loads((out / "elements.json").read_text(encoding="utf-8"))
    assert len(data["elements"]) == 2
    assert data["elements"][0]["center"]
    assert (out / "crops" / "elem_001.png").exists()
    assert len(render_overlay(png, els)) > 0


def test_render_overlay_with_korean_labels(make_png):
    png = _two_button_frame(make_png)
    els = detect_elements(png)
    els[0].label = "전투 시작"
    els[0].kind = "button"
    out = render_overlay(png, els, show_labels=True)
    assert len(out) > 0  # 한글 라벨 렌더링이 예외 없이 PNG를 반환
