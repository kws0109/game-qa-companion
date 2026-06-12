from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QVBoxLayout, QWidget,
)

from companion.gui.util import list_game_configs


class CapturePanel(QWidget):
    """캡처 탭 — CLI capture를 별도 프로세스로 구동 (UI 비블로킹, 중지 안전)."""

    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.proc: QProcess | None = None
        self.start_ts = 0.0
        self.session_dir: Path | None = None
        self._build()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.config_combo = QComboBox()
        self.reload_configs()
        form.addRow("게임 config", self.config_combo)

        src_row = QHBoxLayout()
        self.src_windows = QRadioButton("PC (windows)")
        self.src_windows.setChecked(True)
        self.src_adb = QRadioButton("모바일 (adb)")
        src_row.addWidget(self.src_windows)
        src_row.addWidget(self.src_adb)
        src_row.addStretch()
        src_wrap = QWidget()
        src_wrap.setLayout(src_row)
        form.addRow("입력 소스", src_wrap)

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.5, 60.0)
        self.interval.setValue(2.0)
        self.interval.setSuffix(" 초")
        form.addRow("캡처 간격", self.interval)

        self.duration = QDoubleSpinBox()
        self.duration.setRange(10, 21600)
        self.duration.setValue(1800)
        self.duration.setSuffix(" 초")
        form.addRow("최대 길이", self.duration)
        lay.addLayout(form)

        self.start_btn = QPushButton("캡처 시작")
        self.start_btn.clicked.connect(self._toggle)
        lay.addWidget(self.start_btn)

        self.status = QLabel("대기 — 캡처 중에는 게임 창을 전면에 두세요 (관찰 전용, 입력 주입 없음)")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.preview = QLabel("미리보기")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(320)
        lay.addWidget(self.preview, stretch=1)

    def reload_configs(self) -> None:
        self.config_combo.clear()
        for p in list_game_configs(self.root):
            self.config_combo.addItem(p.stem, userData=str(p))

    def _toggle(self) -> None:
        if self.proc is not None:
            self.proc.kill()  # 프레임·manifest는 매장 저장이라 안전
            return
        cfg = self.config_combo.currentData()
        if not cfg:
            self.status.setText("configs/ 에 게임 yaml이 없습니다")
            return
        source = "windows" if self.src_windows.isChecked() else "adb"
        args = ["-m", "companion.cli", "capture", "--source", source, "--game", cfg,
                "--interval", str(self.interval.value()),
                "--duration", str(self.duration.value()),
                "--out", str(self.root / "sessions")]
        self.start_ts = time.time()
        self.session_dir = None
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(self.root))
        self.proc.finished.connect(self._on_finished)
        self.proc.start(sys.executable, args)
        self.start_btn.setText("캡처 중지")
        self.status.setText("캡처 시작…")
        self.timer.start()

    def _on_finished(self) -> None:
        self.timer.stop()
        self.proc = None
        self.start_btn.setText("캡처 시작")
        self._poll()
        done = f" — 종료. 세션: {self.session_dir.name}" if self.session_dir else " — 종료"
        self.status.setText(self.status.text().split(" — ")[0] + done)

    def _find_session(self) -> Path | None:
        base = self.root / "sessions"
        if not base.exists():
            return None
        dirs = [d for d in base.iterdir()
                if d.is_dir() and d.stat().st_mtime >= self.start_ts - 2]
        return max(dirs, key=lambda d: d.name) if dirs else None

    def _poll(self) -> None:
        if self.session_dir is None:
            self.session_dir = self._find_session()
        if self.session_dir is None:
            return
        manifest = self.session_dir / "manifest.json"
        if not manifest.exists():
            return
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return  # 저장 중 경합 — 다음 틱에 재시도
        frames = data.get("frames", [])
        elapsed = int(time.time() - self.start_ts)
        self.status.setText(f"프레임 {len(frames)}장 · 경과 {elapsed // 60}분 {elapsed % 60}초"
                            f" · 세션 {self.session_dir.name}")
        if frames:
            pix = QPixmap(str(self.session_dir / frames[-1]["file"]))
            if not pix.isNull():
                self.preview.setPixmap(pix.scaled(
                    self.preview.width(), self.preview.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
