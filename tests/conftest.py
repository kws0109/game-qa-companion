import cv2
import numpy as np
import pytest


def png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (200, 120),
              rect: tuple[int, int, int, int] | None = None,
              rect_color: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    """단색 배경 PNG. rect=(x1,y1,x2,y2) 주면 해당 영역을 rect_color로 칠함."""
    img = np.full((size[1], size[0], 3), color[::-1], dtype=np.uint8)  # BGR
    if rect:
        x1, y1, x2, y2 = rect
        img[y1:y2, x1:x2] = rect_color[::-1]
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def make_png():
    return png_bytes
