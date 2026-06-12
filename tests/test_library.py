import json
from pathlib import Path

from companion.library import ElementLibrary
from companion.providers.base import FakeProvider
from companion.vision.elements import apply_library, detect_elements, label_elements
from companion.vision.ocr import crop


def _frame_with_button(make_png) -> bytes:
    return make_png((10, 10, 10), size=(300, 200), rect=(60, 50, 140, 90))


def test_add_and_roundtrip(tmp_path: Path, make_png):
    png = _frame_with_button(make_png)
    lib = ElementLibrary(tmp_path, "Night Crows")
    eid = lib.add("메인 HUD", "전투 버튼", "button", (60, 50, 140, 90), (100, 70),
                  crop(png, (60, 50, 140, 90)))
    # 디스크 재로드에도 유지
    lib2 = ElementLibrary(tmp_path, "Night Crows")
    screens = lib2.tree()
    assert "메인 HUD" in screens
    rec = lib2.all_elements()[0][2]
    assert rec["name"] == "전투 버튼" and rec["kind"] == "button"
    assert (lib2.dir / "templates" / f"{eid}.png").exists()


def test_duplicate_names_get_unique_ids(tmp_path: Path, make_png):
    lib = ElementLibrary(tmp_path, "G")
    a = lib.add("HUD", "버튼", "button", (0, 0, 10, 10), (5, 5), None)
    b = lib.add("HUD", "버튼", "button", (20, 20, 30, 30), (25, 25), None)
    assert a != b and len(lib.all_elements()) == 2


def test_remove_element(tmp_path: Path):
    lib = ElementLibrary(tmp_path, "G")
    eid = lib.add("HUD", "버튼", "button", (0, 0, 10, 10), (5, 5), None)
    lib.remove("HUD", eid)
    assert lib.all_elements() == []
    assert "HUD" not in lib.tree()  # 빈 화면 그룹 정리


def test_apply_library_confirms_detected_element(tmp_path: Path, make_png):
    png = _frame_with_button(make_png)
    lib = ElementLibrary(tmp_path, "G")
    lib.add("HUD", "전투 버튼", "button", (60, 50, 140, 90), (100, 70),
            crop(png, (60, 50, 140, 90)))
    els = apply_library(png, detect_elements(png), lib)
    confirmed = [e for e in els if e.confirmed]
    assert len(confirmed) == 1
    assert confirmed[0].label == "전투 버튼" and confirmed[0].kind == "button"


def test_llm_cannot_override_confirmed(tmp_path: Path, make_png):
    """안전장치 핵심 — LLM이 확정 요소를 다른 이름으로 주장해도 코드가 무시한다."""
    png = _frame_with_button(make_png)
    lib = ElementLibrary(tmp_path, "G")
    lib.add("HUD", "전투 버튼", "button", (60, 50, 140, 90), (100, 70),
            crop(png, (60, 50, 140, 90)))
    els = apply_library(png, detect_elements(png), lib)
    target_id = next(e.id for e in els if e.confirmed)
    provider = FakeProvider(responses=[json.dumps({"elements": [
        {"id": target_id, "role": "minimap", "name": "미니맵(오판)"}]})])
    labeled = label_elements(els, Path("annotated.png"), provider)
    e = next(e for e in labeled if e.id == target_id)
    assert e.label == "전투 버튼" and e.kind == "button"  # 오판이 침투하지 못함
