from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from companion.gui.util import list_game_configs, list_sessions
from companion.gui.workers import FuncWorker


def _run_inspect(root: Path, mode: str, image_path: str | None, cfg_path: str | None,
                 stable_session: Path | None, threshold: float,
                 use_ocr: bool, use_llm: bool):
    from companion.vision.elements import detect_elements, label_elements, save_inspection
    if mode == "image":
        png = Path(image_path).read_bytes()
    else:
        cfg = None
        if cfg_path:
            from companion.config import GameConfig
            cfg = GameConfig.load(cfg_path)
        if mode == "windows":
            from companion.capture.windows import WindowsCapture
            png = WindowsCapture(window_title=cfg.capture_window_title if cfg else None).grab()
        else:
            from companion.capture.adb import AdbCapture
            png = AdbCapture(serial=cfg.capture_adb_serial if cfg else None).grab()
    mask = None
    if stable_session is not None:
        from companion.vision.elements import stability_mask
        mask = stability_mask(stable_session, std_threshold=threshold)
    engine = None
    if use_ocr:
        from companion.vision.ocr import OcrEngine
        engine = OcrEngine()
    elements = detect_elements(png, ocr_engine=engine, mask=mask)
    out = save_inspection(root / "inspections" / datetime.now().strftime("%Y%m%d_%H%M%S"),
                          png, elements)
    if use_llm and elements:
        from companion.providers.claude_agent import ClaudeAgentProvider
        elements = label_elements(elements, out / "annotated.png", ClaudeAgentProvider())
        save_inspection(out, png, elements)
    return out, elements


class InspectPanel(QWidget):
    """Inspect 탭 — 화면 → UI 요소 카탈로그 (좌표·하이라이트·크롭). 스크립트 작성 보조."""

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self._worker: FuncWorker | None = None
        self.out_dir: Path | None = None
        self.elements: list = []
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        form = QFormLayout()

        src_row = QHBoxLayout()
        self.src_windows = QRadioButton("PC 화면")
        self.src_windows.setChecked(True)
        self.src_adb = QRadioButton("모바일 (adb)")
        self.src_image = QRadioButton("이미지 파일")
        for w in (self.src_windows, self.src_adb, self.src_image):
            src_row.addWidget(w)
        self.image_edit = QLineEdit()
        self.image_edit.setPlaceholderText("이미지 파일 경로")
        browse = QPushButton("찾기…")
        browse.clicked.connect(self._browse)
        src_row.addWidget(self.image_edit, stretch=1)
        src_row.addWidget(browse)
        wrap = QWidget()
        wrap.setLayout(src_row)
        form.addRow("입력", wrap)

        self.config_combo = QComboBox()
        self.config_combo.addItem("(없음)", userData=None)
        for p in list_game_configs(self.root):
            self.config_combo.addItem(p.stem, userData=str(p))
        form.addRow("게임 config", self.config_combo)

        stable_row = QHBoxLayout()
        self.stable_combo = QComboBox()
        self.stable_combo.addItem("(사용 안 함)", userData=None)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(5.0, 80.0)
        self.threshold.setValue(30.0)
        stable_row.addWidget(self.stable_combo, stretch=1)
        stable_row.addWidget(QLabel("분산 임계값"))
        stable_row.addWidget(self.threshold)
        wrap2 = QWidget()
        wrap2.setLayout(stable_row)
        form.addRow("안정성 마스크 세션", wrap2)

        opt_row = QHBoxLayout()
        self.ocr_check = QCheckBox("OCR 텍스트 요소")
        self.llm_check = QCheckBox("LLM 역할·이름 라벨링 (claude 구독, 화면당 1회)")
        opt_row.addWidget(self.ocr_check)
        opt_row.addWidget(self.llm_check)
        opt_row.addStretch()
        wrap3 = QWidget()
        wrap3.setLayout(opt_row)
        form.addRow("옵션", wrap3)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("요소 카탈로그 생성")
        self.run_btn.clicked.connect(self._run)
        self.open_btn = QPushButton("카탈로그 폴더 열기")
        self.open_btn.clicked.connect(self._open_folder)
        self.open_btn.setEnabled(False)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.open_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.annotated = QLabel("결과 이미지")
        self.annotated.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll = QScrollArea()
        scroll.setWidget(self.annotated)
        scroll.setWidgetResizable(True)
        split.addWidget(scroll)

        right = QWidget()
        rlay = QVBoxLayout(right)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["id", "종류", "라벨", "중심 좌표"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_crop)
        rlay.addWidget(self.table, stretch=1)
        self.crop_view = QLabel("요소 선택 시 크롭 미리보기")
        self.crop_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_view.setMinimumHeight(120)
        rlay.addWidget(self.crop_view)
        split.addWidget(right)
        split.setSizes([700, 400])
        lay.addWidget(split, stretch=1)

        self.status = QLabel("")
        lay.addWidget(self.status)

    def reload_sessions(self) -> None:
        self.stable_combo.clear()
        self.stable_combo.addItem("(사용 안 함)", userData=None)
        for s in list_sessions(self.root):
            self.stable_combo.addItem(f"{s['name']} ({s['game']})", userData=str(s["path"]))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "스크린샷 선택", "", "Images (*.png *.jpg)")
        if path:
            self.image_edit.setText(path)
            self.src_image.setChecked(True)

    def _run(self) -> None:
        mode = "image" if self.src_image.isChecked() else (
            "windows" if self.src_windows.isChecked() else "adb")
        if mode == "image" and not self.image_edit.text().strip():
            self.status.setText("이미지 파일을 선택하세요")
            return
        stable = self.stable_combo.currentData()
        self._worker = FuncWorker(
            _run_inspect, self.root, mode, self.image_edit.text().strip() or None,
            self.config_combo.currentData(), Path(stable) if stable else None,
            self.threshold.value(), self.ocr_check.isChecked(), self.llm_check.isChecked())
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self.status.setText)
        self.run_btn.setEnabled(False)
        self.status.setText("분석 중…")
        self._worker.start()

    def _on_done(self, payload) -> None:
        self.out_dir, self.elements = payload
        self.run_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.status.setText(f"요소 {len(self.elements)}개 — {self.out_dir}")
        pix = QPixmap(str(self.out_dir / "annotated.png"))
        self.annotated.setPixmap(pix.scaledToWidth(
            900, Qt.TransformationMode.SmoothTransformation))
        self.table.setRowCount(len(self.elements))
        for r, e in enumerate(self.elements):
            for c, val in enumerate([str(e.id), e.kind, e.label,
                                     f"({e.center[0]}, {e.center[1]})"]):
                self.table.setItem(r, c, QTableWidgetItem(val))

    def _show_crop(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or self.out_dir is None:
            return
        e = self.elements[rows[0].row()]
        crop = self.out_dir / "crops" / f"elem_{e.id:03d}.png"
        if crop.exists():
            pix = QPixmap(str(crop))
            self.crop_view.setPixmap(pix.scaled(
                self.crop_view.width(), max(110, self.crop_view.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def _open_folder(self) -> None:
        if self.out_dir:
            os.startfile(self.out_dir)  # Windows 탐색기
