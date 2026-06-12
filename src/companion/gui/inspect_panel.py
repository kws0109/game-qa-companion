from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QRadioButton,
    QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from companion.gui.image_editor import BoxEditor
from companion.gui.util import list_game_configs, list_sessions
from companion.gui.workers import FuncWorker


def _run_inspect(root: Path, mode: str, image_path: str | None, cfg_path: str | None,
                 stable_session: Path | None, threshold: float,
                 use_ocr: bool, use_llm: bool, progress=None, cancel=None):
    def _p(msg: str, pct: int = -1) -> None:
        if progress:
            progress(msg, pct)

    def _check_cancel() -> None:
        if cancel and cancel():
            raise RuntimeError("사용자가 작업을 중단했습니다")

    from companion.vision.elements import (
        apply_library, detect_elements, label_elements, save_inspection,
    )
    cfg = None
    if cfg_path:
        from companion.config import GameConfig
        cfg = GameConfig.load(cfg_path)
    _p("화면 확보 중…", 5)
    if mode == "image":
        png = Path(image_path).read_bytes()
    elif mode == "windows":
        from companion.capture.windows import WindowsCapture
        png = WindowsCapture(window_title=cfg.capture_window_title if cfg else None).grab()
    else:
        from companion.capture.adb import AdbCapture
        png = AdbCapture(serial=cfg.capture_adb_serial if cfg else None).grab()
    _check_cancel()
    mask = None
    if stable_session is not None:
        _p("안정성 마스크 계산 중 (세션 프레임 샘플링)…", 15)
        from companion.vision.elements import stability_mask
        mask = stability_mask(stable_session, std_threshold=threshold)
        _check_cancel()
    engine = None
    if use_ocr:
        _p("OCR 엔진 로드 중 (최초 1회는 모델 로드로 수십 초)…", 35)
        from companion.vision.ocr import OcrEngine
        engine = OcrEngine()
        _check_cancel()
    _p("UI 요소 검출 중 (CV" + (" + OCR" if engine else "") + ")…", 55)
    elements = detect_elements(png, ocr_engine=engine, mask=mask)
    _check_cancel()
    game_name = cfg.name if cfg else "default"
    from companion.library import ElementLibrary
    lib = ElementLibrary(root, game_name)
    if lib.file.exists():  # 확정 요소 = 정답 — 검출 결과에 먼저 강제 적용
        _p("라이브러리 확정 요소 매칭 중…", 70)
        elements = apply_library(png, elements, lib)
    _p("카탈로그 저장 중…", 80)
    out = save_inspection(root / "inspections" / datetime.now().strftime("%Y%m%d_%H%M%S"),
                          png, elements)
    warning = None
    if use_llm and elements:
        _check_cancel()
        _p("LLM 라벨링 중 (Claude 구독 호출 — 수십 초~수 분, 호출 중에는 중단 불가)…", -1)
        try:
            from companion.gui.util import make_provider
            elements = label_elements(elements, out / "annotated.png",
                                      make_provider("claude", root))
            save_inspection(out, png, elements)
        except Exception as e:  # 라벨링은 보강 단계 — 실패해도 CV 카탈로그는 유효
            warning = f"LLM 라벨링 실패({e}) — CV·OCR 결과만 저장됨"
    return out, elements, game_name, warning


class InspectPanel(QWidget):
    """Inspect 탭 — 화면 → UI 요소 카탈로그 (좌표·하이라이트·크롭). 스크립트 작성 보조."""

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self._worker: FuncWorker | None = None
        self.out_dir: Path | None = None
        self.elements: list = []
        self._dirty = False
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
        self.confirm_btn = QPushButton("선택 요소를 라이브러리에 확정 등록")
        self.confirm_btn.clicked.connect(self._confirm_selected)
        self.confirm_btn.setEnabled(False)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.open_btn)
        btn_row.addWidget(self.confirm_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        llay = QVBoxLayout(left)
        self.editor = BoxEditor()
        self.editor.boxSelected.connect(self._on_editor_select)
        self.editor.boxDrawn.connect(self._on_box_drawn)
        scroll = QScrollArea()
        scroll.setWidget(self.editor)
        scroll.setWidgetResizable(False)
        llay.addWidget(scroll, stretch=1)

        edit_row = QHBoxLayout()
        self.delete_btn = QPushButton("선택 삭제 (Del)")
        self.delete_btn.clicked.connect(self._delete_selected)
        self.redraw_btn = QPushButton("박스 다시 그리기")
        self.redraw_btn.setCheckable(True)
        self.redraw_btn.toggled.connect(self._on_redraw_toggled)
        self.save_btn = QPushButton("변경 저장")
        self.save_btn.clicked.connect(self._save_changes)
        self.save_btn.setEnabled(False)
        for b in (self.delete_btn, self.redraw_btn, self.save_btn):
            edit_row.addWidget(b)
        edit_row.addStretch()
        llay.addLayout(edit_row)
        split.addWidget(left)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._delete_selected)

        right = QWidget()
        rlay = QVBoxLayout(right)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["id", "종류", "라벨", "중심 좌표", "확정"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        self.table.itemChanged.connect(self._on_cell_edited)
        rlay.addWidget(self.table, stretch=1)
        self.crop_view = QLabel("요소 선택 시 크롭 미리보기")
        self.crop_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_view.setMinimumHeight(120)
        rlay.addWidget(self.crop_view)
        split.addWidget(right)
        split.setSizes([700, 400])
        lay.addWidget(split, stretch=1)

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximumWidth(260)
        self.cancel_btn = QPushButton("중단")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_run)
        bottom.addWidget(self.status, stretch=1)
        bottom.addWidget(self.progress_bar)
        bottom.addWidget(self.cancel_btn)
        lay.addLayout(bottom)

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
        # 안전장치: config 미설정 실행 차단 — 창 제목 없이 캡처하면 모니터 전체가 잡힌다
        cfg_path = self.config_combo.currentData()
        if not cfg_path:
            self.status.setText("오류: 게임 config를 선택하세요 — 미설정 상태로는 실행할 수 없습니다 "
                                "(configs/ 에 게임 yaml 추가 후 새로고침)")
            return
        if mode == "windows":
            from companion.config import GameConfig
            if not GameConfig.load(cfg_path).capture_window_title:
                self.status.setText("오류: 이 config에 capture.window_title이 없습니다 — "
                                    "게임 창 대신 모니터 전체가 캡처됩니다. yaml에 창 제목을 넣어주세요")
                return
        stable = self.stable_combo.currentData()
        self._worker = FuncWorker(
            _run_inspect, self.root, mode, self.image_edit.text().strip() or None,
            self.config_combo.currentData(), Path(stable) if stable else None,
            self.threshold.value(), self.ocr_check.isChecked(), self.llm_check.isChecked(),
            with_progress=True)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.progress.connect(self._on_progress)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status.setText("시작…")
        self._worker.start()

    def _cancel_run(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.status.setText("중단 요청됨 — 현재 단계가 끝나는 대로 멈춥니다")

    def _on_progress(self, msg: str, pct: int) -> None:
        self.status.setText(msg)
        if pct < 0:
            self.progress_bar.setRange(0, 0)  # 무한 바 — 길이를 모르는 단계
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)

    def _on_failed(self, msg: str) -> None:
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status.setText(("중단됨: " if "중단" in msg else "오류: ") + msg)

    def _on_done(self, payload) -> None:
        self.out_dir, self.elements, self.game_name, warning = payload
        self._dirty = False
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.open_btn.setEnabled(True)
        self.confirm_btn.setEnabled(True)
        self.save_btn.setEnabled(False)
        confirmed = sum(1 for e in self.elements if e.confirmed)
        msg = (f"요소 {len(self.elements)}개 (라이브러리 확정 {confirmed}개 자동 인식)"
               f" — {self.out_dir} · 오탐은 클릭→Del, 누락은 드래그로 추가")
        if warning:
            msg = f"⚠ {warning} · " + msg
        self.status.setText(msg)
        self.editor.load(self.out_dir / "source.png", self.elements)
        self._fill_table()

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.elements))
        for r, e in enumerate(self.elements):
            for c, val in enumerate([str(e.id), e.kind, e.label,
                                     f"({e.center[0]}, {e.center[1]})",
                                     "✓" if e.confirmed else ""]):
                item = QTableWidgetItem(val)
                if c not in (1, 2):  # 종류·라벨만 편집 허용
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)
        self.table.blockSignals(False)
        self.editor.update()

    # --- 편집 동작 -------------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True
        self.save_btn.setEnabled(True)

    def _on_table_select(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        self.editor.set_selected(rows[0].row() if rows else -1)
        self._show_crop()

    def _on_editor_select(self, idx: int) -> None:
        self.table.selectRow(idx)
        item = self.table.item(idx, 0)
        if item:  # 선택 행이 보이도록 자동 스크롤
            self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _on_cell_edited(self, item) -> None:
        e = self.elements[item.row()]
        if item.column() == 1:
            e.kind = item.text().strip() or e.kind
        elif item.column() == 2:
            e.label = item.text().strip()
        self._mark_dirty()
        self.editor.update()

    def _on_redraw_toggled(self, on: bool) -> None:
        self.editor.redraw_mode = on
        self.status.setText("박스 다시 그리기: 요소를 선택한 뒤 이미지에 새 영역을 드래그하세요"
                            if on else "")

    def _on_box_drawn(self, bbox: tuple) -> None:
        from companion.vision.elements import UIElement
        l, t, r, b = bbox
        rows = self.table.selectionModel().selectedRows()
        if self.redraw_btn.isChecked() and rows:  # 선택 요소의 박스 교체
            e = self.elements[rows[0].row()]
            e.bbox = (l, t, r, b)
            e.center = ((l + r) // 2, (t + b) // 2)
            self.redraw_btn.setChecked(False)
        else:  # 누락 요소 수동 추가
            next_id = max((e.id for e in self.elements), default=0) + 1
            self.elements.append(UIElement(next_id, "box", "", (l, t, r, b),
                                           ((l + r) // 2, (t + b) // 2)))
        self._mark_dirty()
        self._fill_table()

    def _delete_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        del self.elements[rows[0].row()]
        self.editor.set_selected(-1)
        self._mark_dirty()
        self._fill_table()
        self.status.setText("요소 삭제됨 — '변경 저장'을 누르면 카탈로그에 반영됩니다")

    def _save_changes(self) -> None:
        if self.out_dir is None:
            return
        from companion.vision.elements import save_inspection
        png = (self.out_dir / "source.png").read_bytes()
        save_inspection(self.out_dir, png, self.elements)  # json·주석 이미지·크롭 재생성
        self._dirty = False
        self.save_btn.setEnabled(False)
        self.editor.load(self.out_dir / "source.png", self.elements)
        self._fill_table()
        self.status.setText(f"저장됨 — 요소 {len(self.elements)}개, {self.out_dir}")

    def _confirm_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or self.out_dir is None:
            self.status.setText("등록할 요소를 테이블에서 선택하세요")
            return
        if self._dirty:
            self._save_changes()  # 수동 추가·수정 박스의 크롭이 있어야 템플릿 등록 가능
        e = self.elements[rows[0].row()]
        from PySide6.QtWidgets import QInputDialog
        from companion.library import ElementLibrary
        lib = ElementLibrary(self.root, getattr(self, "game_name", "default"))
        screens = list(lib.tree().keys()) or ["메인 HUD"]
        screen, ok = QInputDialog.getItem(self, "화면 그룹", "이 요소가 속한 화면:",
                                          screens, 0, editable=True)
        if not ok or not screen.strip():
            return
        name, ok = QInputDialog.getText(self, "요소 이름", "확정 이름:", text=e.label or "")
        if not ok or not name.strip():
            return
        crop_file = self.out_dir / "crops" / f"elem_{e.id:03d}.png"
        crop_png = crop_file.read_bytes() if crop_file.exists() else None
        kind = e.kind if e.kind not in ("box", "text") else "button"
        lib.add(screen.strip(), name.strip(), kind, e.bbox, e.center, crop_png)
        e.confirmed = True
        e.label = name.strip()
        self._fill_table()
        self.status.setText(f"라이브러리 등록: [{screen.strip()}] {name.strip()} "
                            f"— 이후 inspect에서 자동 인식되며 LLM이 덮어쓸 수 없습니다")

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
