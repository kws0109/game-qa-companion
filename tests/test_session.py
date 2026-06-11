from pathlib import Path

from companion.session import Manifest, record_session


class FakeGrabber:
    """단조 증가 색의 PNG를 돌려주는 테스트용 grabber."""

    def __init__(self, make_png):
        self.n = 0
        self.make_png = make_png

    def grab(self) -> bytes:
        self.n += 1
        return self.make_png((self.n % 255, 0, 0))


def test_record_session_writes_frames_and_manifest(tmp_path: Path, make_png):
    out = record_session(FakeGrabber(make_png), tmp_path, game="G", source="fake",
                         interval=0.01, max_frames=5)
    frames_dir = out / "frames"
    assert len(list(frames_dir.glob("*.png"))) == 5
    m = Manifest.load(out)
    assert m.game == "G" and m.source == "fake"
    assert len(m.frames) == 5
    assert m.frames[0].file == "frames/frame_000000.png"
    assert m.frames[4].t >= m.frames[0].t


def test_manifest_roundtrip(tmp_path: Path):
    m = Manifest(game="G", source="adb", started_at="2026-06-12T00:00:00", interval=2.0)
    m.add_frame("frames/frame_000000.png", 0.0)
    m.save(tmp_path)
    loaded = Manifest.load(tmp_path)
    assert loaded.frames[0].file == "frames/frame_000000.png"
