from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QProgressBar, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from companion.gui.util import list_game_configs, list_sessions, make_provider
from companion.gui.workers import FuncWorker


def _run_analyze(session: Path, cfg_path: str, provider_name: str,
                 max_candidates: int, use_ocr: bool, progress=None, cancel=None):
    from companion.analysis.pipeline import analyze_session
    from companion.analysis.report import render_report
    from companion.config import GameConfig
    engine = None
    if use_ocr:
        if progress:
            progress("OCR 엔진 로드 중 (최초 1회는 모델 로드로 수십 초)…", 5)
        from companion.vision.ocr import OcrEngine
        engine = OcrEngine()
    result = analyze_session(session, GameConfig.load(cfg_path), make_provider(provider_name),
                             ocr_engine=engine, max_candidates=max_candidates,
                             progress=progress, cancel=cancel)
    return result, render_report(session)


def _run_import(src: str, base: Path, game: str):
    from companion.capture.artifacts import import_artifacts
    return import_artifacts(src, base, game=game)


def _run_ask(session: Path, question: str):
    from companion.analysis.qa import ask
    return ask(session, question, make_provider("claude"))


class SessionsPanel(QWidget):
    """세션 목록 + 분석 실행 + 리포트 뷰 + 자연어 질의."""

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self._worker: FuncWorker | None = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.clicked.connect(self.refresh)
        self.import_btn = QPushButton("산출물 가져오기…")
        self.import_btn.clicked.connect(self._import)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.import_btn)
        top.addStretch()
        lay.addLayout(top)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["세션", "게임", "프레임", "크기(MB)", "분석"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_report_if_any)
        self.table.setMaximumHeight(180)
        lay.addWidget(self.table)

        ctl = QHBoxLayout()
        self.config_combo = QComboBox()
        for p in list_game_configs(self.root):
            self.config_combo.addItem(p.stem, userData=str(p))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("fake (무료 드라이런)", userData="fake")
        self.provider_combo.addItem("claude (구독 — 실판정)", userData="claude")
        self.max_cand = QSpinBox()
        self.max_cand.setRange(1, 50)
        self.max_cand.setValue(5)
        self.ocr_check = QCheckBox("OCR")
        self.analyze_btn = QPushButton("분석 실행")
        self.analyze_btn.clicked.connect(self._analyze)
        for w in (QLabel("config"), self.config_combo, QLabel("provider"),
                  self.provider_combo, QLabel("후보 상한"), self.max_cand,
                  self.ocr_check, self.analyze_btn):
            ctl.addWidget(w)
        ctl.addStretch()
        lay.addLayout(ctl)

        self.report = QTextBrowser()
        self.report.setOpenExternalLinks(True)
        lay.addWidget(self.report, stretch=1)

        ask_row = QHBoxLayout()
        self.ask_edit = QLineEdit()
        self.ask_edit.setPlaceholderText("세션에 질문 — 예: 정체 구간이 있었나? (claude 구독 사용)")
        self.ask_btn = QPushButton("질문")
        self.ask_btn.clicked.connect(self._ask)
        ask_row.addWidget(self.ask_edit, stretch=1)
        ask_row.addWidget(self.ask_btn)
        lay.addLayout(ask_row)

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

    # --- helpers -------------------------------------------------------
    def refresh(self) -> None:
        self.sessions = list_sessions(self.root)
        self.table.setRowCount(len(self.sessions))
        for r, s in enumerate(self.sessions):
            for c, val in enumerate([s["name"], s["game"], str(s["frames"]),
                                     str(s["size_mb"]), "✓" if s["analyzed"] else ""]):
                self.table.setItem(r, c, QTableWidgetItem(val))

    def _selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        return self.sessions[rows[0].row()] if rows else None

    def _busy(self, msg: str) -> None:
        self.status.setText(msg)
        self.analyze_btn.setEnabled(False)
        self.ask_btn.setEnabled(False)

    def _idle(self, msg: str = "") -> None:
        self.status.setText(msg)
        self.analyze_btn.setEnabled(True)
        self.ask_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

    def _cancel_run(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.status.setText("중단 요청됨 — 현재 단계가 끝나는 대로 멈춥니다")

    def _on_progress(self, msg: str, pct: int) -> None:
        self.status.setText(msg)
        if pct < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)

    def _on_failed(self, msg: str) -> None:
        self._idle(("중단됨: " if "중단" in msg else "오류: ") + msg)

    # --- actions -------------------------------------------------------
    def _import(self) -> None:
        src = QFileDialog.getExistingDirectory(self, "기존 자동화 산출물 디렉토리 선택")
        if not src:
            return
        game, ok = QInputDialog.getText(self, "게임 이름", "이 산출물의 게임 이름:")
        if not ok or not game:
            return
        self._worker = FuncWorker(_run_import, src, self.root / "sessions", game)
        self._worker.done.connect(lambda out: (self.refresh(), self._idle(f"가져옴: {out}")))
        self._worker.failed.connect(self._idle)
        self._busy("산출물 변환 중…")
        self._worker.start()

    def _analyze(self) -> None:
        s = self._selected()
        if not s:
            self._idle("세션을 선택하세요")
            return
        cfg = self.config_combo.currentData()
        if not cfg:
            self._idle("게임 config가 없습니다")
            return
        provider = self.provider_combo.currentData()
        self._worker = FuncWorker(_run_analyze, s["path"], cfg, provider,
                                  self.max_cand.value(), self.ocr_check.isChecked(),
                                  with_progress=True)
        self._worker.done.connect(self._on_analyzed)
        self._worker.failed.connect(self._on_failed)
        self._worker.progress.connect(self._on_progress)
        self._busy("분석 시작…")
        self.cancel_btn.setEnabled(True)
        self._worker.start()

    def _on_analyzed(self, payload) -> None:
        result, report_path = payload
        self.refresh()
        self._load_report(Path(report_path).parent)
        self._idle(f"분석 완료 — 후보 {len(result['candidates'])}건")

    def _show_report_if_any(self) -> None:
        s = self._selected()
        if s and (s["path"] / "report.md").exists():
            self._load_report(s["path"])
        else:
            self.report.setMarkdown("*(이 세션은 아직 분석 전입니다 — 분석 실행을 누르세요)*")

    def _load_report(self, session: Path) -> None:
        text = (session / "report.md").read_text(encoding="utf-8")
        # 상대 이미지 경로 → 절대 file URI (QTextBrowser 렌더링용)
        text = text.replace("](frames/", f"]({session.resolve().as_uri()}/frames/")
        self.report.setMarkdown(text)

    def _ask(self) -> None:
        s = self._selected()
        q = self.ask_edit.text().strip()
        if not s or not q:
            self._idle("세션 선택 + 질문 입력이 필요합니다")
            return
        if not (s["path"] / "analysis.json").exists():
            self._idle("분석을 먼저 실행하세요")
            return
        self._worker = FuncWorker(_run_ask, s["path"], q)
        self._worker.done.connect(
            lambda a: (self.report.append(f"\n\n---\n**Q. {q}**\n\n{a}"), self._idle("응답 수신")))
        self._worker.failed.connect(self._idle)
        self._busy("질의 중… (claude 구독 사용)")
        self._worker.start()
