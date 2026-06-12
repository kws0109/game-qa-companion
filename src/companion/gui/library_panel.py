from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from companion.library import ElementLibrary


class LibraryPanel(QWidget):
    """라이브러리 탭 — 게임 → 화면 → 확정 요소 트리. 재사용 가능한 정답 저장소 뷰."""

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.lib: ElementLibrary | None = None
        self._build()
        self.reload_games()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.game_combo = QComboBox()
        self.game_combo.currentIndexChanged.connect(self._load_tree)
        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.clicked.connect(self.reload_games)
        self.delete_btn = QPushButton("선택 요소 삭제")
        self.delete_btn.clicked.connect(self._delete)
        top.addWidget(QLabel("게임"))
        top.addWidget(self.game_combo, stretch=1)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.delete_btn)
        lay.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["화면 / 요소", "종류", "중심 좌표", "확정 시각"])
        self.tree.itemSelectionChanged.connect(self._show_preview)
        split.addWidget(self.tree)

        right = QWidget()
        rlay = QVBoxLayout(right)
        self.preview = QLabel("요소 선택 시 템플릿 미리보기")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(260, 160)
        self.meta = QLabel("")
        self.meta.setWordWrap(True)
        rlay.addWidget(self.preview, stretch=1)
        rlay.addWidget(self.meta)
        split.addWidget(right)
        split.setSizes([700, 350])
        lay.addWidget(split, stretch=1)

        self.status = QLabel("요소는 Inspect 탭에서 '확정 등록'으로 추가됩니다")
        lay.addWidget(self.status)

    def reload_games(self) -> None:
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        base = self.root / "library"
        if base.exists():
            for d in sorted(base.iterdir()):
                f = d / "elements.json"
                if f.exists():
                    try:
                        game = json.loads(f.read_text(encoding="utf-8")).get("game", d.name)
                    except json.JSONDecodeError:
                        continue
                    self.game_combo.addItem(game)
        self.game_combo.blockSignals(False)
        self._load_tree()

    def _load_tree(self) -> None:
        self.tree.clear()
        game = self.game_combo.currentText()
        if not game:
            self.lib = None
            return
        self.lib = ElementLibrary(self.root, game)
        for screen, body in self.lib.tree().items():
            top = QTreeWidgetItem([screen, "", "", ""])
            self.tree.addTopLevelItem(top)
            for eid, rec in body["elements"].items():
                child = QTreeWidgetItem([
                    rec["name"], rec["kind"],
                    f"({rec['center'][0]}, {rec['center'][1]})",
                    rec.get("confirmed_at", "")])
                child.setData(0, Qt.ItemDataRole.UserRole, (screen, eid))
                top.addChild(child)
            top.setExpanded(True)

    def _selected_ref(self) -> tuple[str, str] | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def _show_preview(self) -> None:
        ref = self._selected_ref()
        if not ref or self.lib is None:
            return
        screen, eid = ref
        rec = self.lib.tree()[screen]["elements"][eid]
        self.meta.setText(f"id: {eid} · bbox: {rec['bbox']} · 화면: {screen}")
        tpl = self.lib.template_bytes(rec)
        if tpl:
            pix = QPixmap()
            pix.loadFromData(tpl)
            self.preview.setPixmap(pix.scaled(
                self.preview.width(), self.preview.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def _delete(self) -> None:
        ref = self._selected_ref()
        if not ref or self.lib is None:
            self.status.setText("삭제할 요소를 트리에서 선택하세요")
            return
        screen, eid = ref
        name = self.lib.tree()[screen]["elements"][eid]["name"]
        if QMessageBox.question(self, "삭제 확인",
                                f"[{screen}] {name} 을(를) 라이브러리에서 삭제할까요?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.lib.remove(screen, eid)
        self._load_tree()
        self.status.setText(f"삭제됨: [{screen}] {name}")
