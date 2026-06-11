from dataclasses import dataclass

import pytest

from companion.capture.windows import WindowsCapture


@dataclass
class FakeWin:
    title: str
    width: int
    height: int
    isMinimized: bool = False
    left: int = 0
    top: int = 0


def test_pick_window_prefers_largest_visible():
    launcher = FakeWin("NIGHT CROWS", 400, 300)
    game = FakeWin("NIGHT CROWS(1)  ", 1920, 1080)
    assert WindowsCapture._pick_window([launcher, game]) is game


def test_pick_window_skips_minimized():
    minimized = FakeWin("NIGHT CROWS(1)  ", 1920, 1080, isMinimized=True)
    launcher = FakeWin("NIGHT CROWS", 400, 300)
    assert WindowsCapture._pick_window([minimized, launcher]) is launcher


def test_pick_window_all_minimized_raises():
    with pytest.raises(RuntimeError, match="minimized"):
        WindowsCapture._pick_window([FakeWin("G", 100, 100, isMinimized=True)])
