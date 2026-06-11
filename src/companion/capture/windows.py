from __future__ import annotations

import cv2
import numpy as np


class WindowsCapture:
    """mss 기반 화면 캡처. window_title을 주면 해당 창 영역만, 없으면 주 모니터 전체.

    window_title은 부분 일치 — "NIGHT CROW"로 "NIGHT CROWS(1)  " 같은 변형을 흡수.
    매칭 창이 여러 개면(본창+런처 등) 최소화되지 않은 것 중 면적이 가장 큰 창을 고른다.
    매 grab마다 mss 인스턴스를 새로 열고 닫는다 — stateless 원칙(장시간 루프 안전).
    입력 주입 기능 없음: 관찰 전용.

    한계: mss는 창 표면이 아니라 화면 좌표 영역을 찍는다 — 캡처 중 대상 창이 다른 창에
    가려지면 가린 화면이 찍히므로, 세션 동안 게임 창을 전면에 둘 것 (사람 plays 중엔 자연 충족).
    """

    def __init__(self, window_title: str | None = None):
        self.window_title = window_title

    @staticmethod
    def _pick_window(wins: list):
        visible = [w for w in wins
                   if w.title and not w.isMinimized and w.width > 0 and w.height > 0]
        if not visible:
            raise RuntimeError(
                "matching window is minimized or zero-size — bring the game window to front")
        return max(visible, key=lambda w: w.width * w.height)

    def _bbox(self) -> dict | int:
        if not self.window_title:
            return 1  # mss monitor index 1 = primary
        import pygetwindow as gw
        wins = gw.getWindowsWithTitle(self.window_title)
        if not wins:
            raise RuntimeError(f"window not found: {self.window_title!r}")
        w = self._pick_window(wins)
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
