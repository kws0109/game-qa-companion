from __future__ import annotations

import cv2
import numpy as np


class WindowsCapture:
    """mss 기반 화면 캡처. window_title을 주면 해당 창 영역만, 없으면 주 모니터 전체.

    window_title은 부분 일치 — "NIGHT CROW"로 "NIGHT CROW(1)" 같은 suffix 변동을 흡수.
    매 grab마다 mss 인스턴스를 새로 열고 닫는다 — stateless 원칙(장시간 루프 안전).
    입력 주입 기능 없음: 관찰 전용.
    """

    def __init__(self, window_title: str | None = None):
        self.window_title = window_title

    def _bbox(self) -> dict | int:
        if not self.window_title:
            return 1  # mss monitor index 1 = primary
        import pygetwindow as gw
        wins = [w for w in gw.getWindowsWithTitle(self.window_title) if w.title]
        if not wins:
            raise RuntimeError(f"window not found: {self.window_title!r}")
        w = wins[0]
        return {"left": w.left, "top": w.top, "width": w.width, "height": w.height}

    def grab(self) -> bytes:
        import mss
        with mss.mss() as sct:
            bbox = self._bbox()
            shot = sct.grab(sct.monitors[bbox] if isinstance(bbox, int) else bbox)
            img = np.asarray(shot)[:, :, :3]  # BGRA → BGR
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                raise RuntimeError("png encode failed")
            return buf.tobytes()
