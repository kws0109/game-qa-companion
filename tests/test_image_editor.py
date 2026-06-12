import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from companion.vision.elements import UIElement


def _editor_with_two_boxes(tmp_path: Path, make_png):
    from PySide6.QtWidgets import QApplication
    from companion.gui.image_editor import BoxEditor
    QApplication.instance() or QApplication([])
    src = tmp_path / "source.png"
    src.write_bytes(make_png((0, 0, 0), size=(400, 300)))
    els = [
        UIElement(1, "box", "큰 패널", (10, 10, 200, 200), (105, 105)),
        UIElement(2, "button", "작은 버튼", (50, 50, 100, 90), (75, 70)),
    ]
    ed = BoxEditor()
    ed.load(src, els)
    return ed


def test_hit_test_prefers_smaller_overlapping_box(tmp_path, make_png):
    ed = _editor_with_two_boxes(tmp_path, make_png)
    assert ed.hit_test(70, 70) == 1   # 겹치는 지점 — 작은 버튼 우선
    assert ed.hit_test(150, 150) == 0  # 큰 패널만 걸리는 지점
    assert ed.hit_test(390, 290) == -1  # 빈 곳


def test_hit_test_includes_number_tag_zone(tmp_path, make_png):
    ed = _editor_with_two_boxes(tmp_path, make_png)
    # 큰 패널(10,10)의 번호 태그 = 박스 바로 위 좌측 — 클릭 인식돼야 함
    assert ed.hit_test(15, 5) == 0
    # 박스에서 먼 위쪽 빈 공간은 여전히 미인식
    assert ed.hit_test(300, 5) == -1


def test_load_fits_viewport(tmp_path, make_png):
    from PySide6.QtWidgets import QApplication
    from companion.gui.image_editor import BoxEditor
    QApplication.instance() or QApplication([])
    src = tmp_path / "wide.png"
    src.write_bytes(make_png((0, 0, 0), size=(1800, 600)))
    app = QApplication.instance()
    ed = BoxEditor()
    ed.show()  # 숨김 위젯은 resizeEvent를 받지 않음 — offscreen에서도 show 필요
    ed.resize(900, 600)
    app.processEvents()
    ed.load(src, [])
    assert abs(ed._scale - 0.5) < 0.01  # 1800px 폭 → 900px 뷰포트에 맞춤 (스크롤 없음)
    ed.resize(450, 600)
    app.processEvents()
    assert abs(ed._scale - 0.25) < 0.01  # 창 줄이면 따라 축소
