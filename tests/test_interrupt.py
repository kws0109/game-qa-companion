from pathlib import Path

from companion.session import Manifest, record_session


class InterruptingGrabber:
    """3번째 grab에서 Ctrl+C 시뮬레이션."""

    def __init__(self, make_png, fail_at: int = 3):
        self.n = 0
        self.fail_at = fail_at
        self.make_png = make_png

    def grab(self) -> bytes:
        self.n += 1
        if self.n >= self.fail_at:
            raise KeyboardInterrupt
        return self.make_png((self.n * 50 % 255, 0, 0))


def test_ctrl_c_keeps_session_and_returns_cleanly(tmp_path: Path, make_png):
    out = record_session(InterruptingGrabber(make_png), tmp_path, game="G",
                         source="fake", interval=0.01, max_frames=10)
    m = Manifest.load(out)  # manifest가 살아 있고
    assert len(m.frames) == 2  # 중단 전 프레임 2장이 보존됨
    assert (out / m.frames[1].file).exists()
