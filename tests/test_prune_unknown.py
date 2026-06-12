from pathlib import Path

from companion.vision.elements import UIElement, prune_unknown, save_inspection


def _els() -> list[UIElement]:
    return [
        UIElement(1, "button", "전투", (10, 10, 50, 40), (30, 25)),
        UIElement(2, "unknown", "", (60, 10, 120, 60), (90, 35)),          # 배경 오검출
        UIElement(3, "unknown", "정답", (10, 80, 60, 120), (35, 100),
                  confirmed=True),                                          # 확정은 보호
        UIElement(4, "unknown", "", (200, 200, 260, 240), (230, 220)),
    ]


def test_prune_removes_unknown_keeps_confirmed():
    kept, removed = prune_unknown(_els())
    assert removed == 2
    kinds = [(e.kind, e.confirmed) for e in kept]
    assert ("button", False) in kinds and ("unknown", True) in kinds
    assert [e.id for e in kept] == [1, 2]  # id 재부여


def test_save_inspection_clears_stale_crops(tmp_path: Path, make_png):
    png = make_png((0, 0, 0), size=(300, 260))
    out = tmp_path / "insp"
    (out / "crops").mkdir(parents=True)
    (out / "crops" / "elem_099.png").write_bytes(b"stale")
    save_inspection(out, png, [UIElement(1, "button", "", (10, 10, 50, 40), (30, 25))])
    assert not (out / "crops" / "elem_099.png").exists()  # 잔여 크롭 정리
    assert (out / "crops" / "elem_001.png").exists()
