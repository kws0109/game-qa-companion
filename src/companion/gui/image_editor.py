from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel


class BoxEditor(QLabel):
    """검출 박스를 직접 편집하는 이미지 뷰 — 클릭=선택, 빈 곳 드래그=새 박스.

    좌표는 항상 원본 이미지 픽셀 기준으로 다루고, 표시 스케일만 변환한다.
    redraw_mode가 켜져 있으면 다음 드래그가 선택 요소의 박스를 교체한다.
    """

    boxDrawn = Signal(tuple)   # (l, t, r, b) — 원본 이미지 좌표
    boxSelected = Signal(int)  # elements 리스트 인덱스

    MAX_WIDTH = 900

    def __init__(self):
        super().__init__("결과 이미지")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._pix: QPixmap | None = None
        self._scale = 1.0
        self.elements: list = []
        self.selected = -1
        self.redraw_mode = False
        self._drag_start: QPoint | None = None
        self._drag_cur: QPoint | None = None

    # --- state ---------------------------------------------------------
    def load(self, source_png: str | Path, elements: list) -> None:
        orig = QPixmap(str(source_png))
        self._scale = min(1.0, self.MAX_WIDTH / max(1, orig.width()))
        self._pix = orig.scaledToWidth(int(orig.width() * self._scale),
                                       Qt.TransformationMode.SmoothTransformation)
        self.elements = elements
        self.selected = -1
        self.setFixedSize(self._pix.size())
        self.update()

    def set_selected(self, idx: int) -> None:
        self.selected = idx
        self.update()

    def hit_test(self, x: int, y: int) -> int:
        """원본 좌표 (x,y)에 걸리는 요소 인덱스 — 겹치면 면적이 작은 것 우선. 없으면 -1.

        박스 위에 그려지는 번호 태그 영역도 클릭 대상에 포함한다.
        """
        hits = [(i, e) for i, e in enumerate(self.elements)
                if e.bbox[0] <= x <= e.bbox[2] and e.bbox[1] <= y <= e.bbox[3]]
        if hits:
            return min(hits, key=lambda t: (t[1].bbox[2] - t[1].bbox[0])
                       * (t[1].bbox[3] - t[1].bbox[1]))[0]
        tag_w = 30 / self._scale
        tag_h = 20 / self._scale
        for i, e in enumerate(self.elements):
            l, t = e.bbox[0], e.bbox[1]
            if l <= x <= l + tag_w and t - tag_h <= y <= t:
                return i
        return -1

    # --- painting ------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._pix is None:
            return super().paintEvent(event)
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pix)
        for i, e in enumerate(self.elements):
            l, t, r, b = (int(v * self._scale) for v in e.bbox)
            if i == self.selected:
                color = QColor(255, 70, 70)      # 선택 = 빨강
            elif getattr(e, "confirmed", False):
                color = QColor(0, 160, 255)      # 확정 = 파랑
            else:
                color = QColor(0, 220, 90)       # 후보 = 초록
            p.setPen(QPen(color, 2))
            p.drawRect(QRect(l, t, r - l, b - t))
            p.fillRect(l, t - 16, 26, 16, color)
            p.setPen(QPen(QColor(0, 0, 0)))
            p.drawText(l + 4, t - 3, str(e.id))
        if self._drag_start and self._drag_cur:
            p.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRect(self._drag_start, self._drag_cur).normalized())
        p.end()

    # --- mouse ---------------------------------------------------------
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if self._pix is not None and ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start = ev.position().toPoint()
            self._drag_cur = self._drag_start

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._drag_start is not None:
            self._drag_cur = ev.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if self._drag_start is None or self._pix is None:
            return
        start, end = self._drag_start, ev.position().toPoint()
        self._drag_start = self._drag_cur = None
        self.update()
        if (start - end).manhattanLength() < 6:  # 클릭 = 선택
            x, y = int(start.x() / self._scale), int(start.y() / self._scale)
            idx = self.hit_test(x, y)
            if idx >= 0:
                self.boxSelected.emit(idx)
            return
        rect = QRect(start, end).normalized()
        l = int(rect.left() / self._scale)
        t = int(rect.top() / self._scale)
        r = int(rect.right() / self._scale)
        b = int(rect.bottom() / self._scale)
        if r - l >= 8 and b - t >= 8:  # 너무 작은 드래그는 무시
            self.boxDrawn.emit((l, t, r, b))
