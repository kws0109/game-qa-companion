from pathlib import Path

from companion.session import Manifest
from companion.vision.analyzer import find_stalls, frame_diff, match_template


def _write_session(tmp_path: Path, pngs: list[bytes], dt: float = 2.0) -> Path:
    d = tmp_path / "s"
    (d / "frames").mkdir(parents=True)
    m = Manifest(game="G", source="fake", started_at="2026-06-12T00:00:00", interval=dt)
    for i, b in enumerate(pngs):
        name = f"frames/frame_{i:06d}.png"
        (d / name).write_bytes(b)
        m.add_frame(name, i * dt)
    m.save(d)
    return d


def test_frame_diff_zero_for_identical(make_png):
    a = make_png((10, 10, 10))
    assert frame_diff(a, a) == 0.0


def test_frame_diff_positive_for_different(make_png):
    assert frame_diff(make_png((0, 0, 0)), make_png((200, 200, 200))) > 50


def test_find_stalls_detects_frozen_run(tmp_path, make_png):
    frozen = make_png((30, 30, 30))
    pngs = [make_png((i * 50 % 255, 0, 0)) for i in range(2)] + [frozen] * 5 \
        + [make_png((0, i * 60 % 255, 0)) for i in range(2)]
    d = _write_session(tmp_path, pngs)
    stalls = find_stalls(d, threshold=2.0, min_run=4)
    assert len(stalls) == 1
    assert stalls[0]["start_t"] == 4.0  # frozen 구간 시작 (index 2 * dt 2.0)
    assert stalls[0]["frame_count"] >= 4


def test_match_template_finds_white_box(make_png):
    frame = make_png((0, 0, 0), size=(200, 120), rect=(50, 40, 90, 70))
    tpl = make_png((255, 255, 255), size=(40, 30))
    score, (x, y) = match_template(frame, tpl)
    assert score > 0.9
    assert abs(x - 50) <= 2 and abs(y - 40) <= 2
