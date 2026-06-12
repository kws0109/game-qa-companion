from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout,
)

from companion.gui.claude_status import claude_status
from companion.gui.settings import AppSettings

_MODELS = [
    ("기본 (Claude Code 설정 따름 — 권장)", None),
    ("opus", "opus"),
    ("sonnet", "sonnet"),
    ("haiku", "haiku"),
]


class SettingsDialog(QDialog):
    """Claude 연결 설정 — 계정 상태·로그인 터미널·모델·턴 한도."""

    def __init__(self, root: Path, parent=None):
        super().__init__(parent)
        self.root = root
        self.setWindowTitle("Claude 연결 설정")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)

        self.account_label = QLabel("")
        self.account_label.setWordWrap(True)
        lay.addWidget(self.account_label)

        self.login_btn = QPushButton("로그인 / 계정 전환 터미널 열기")
        self.login_btn.setToolTip("새 터미널에서 claude를 실행합니다 — 그 안에서 /login 으로 "
                                  "로그인·계정 전환, /logout 으로 로그아웃하세요. "
                                  "완료 후 이 창의 '상태 새로고침'을 누르면 반영됩니다.")
        self.login_btn.clicked.connect(self._open_terminal)
        lay.addWidget(self.login_btn)

        self.refresh_btn = QPushButton("상태 새로고침")
        self.refresh_btn.clicked.connect(self._refresh)
        lay.addWidget(self.refresh_btn)

        form = QFormLayout()
        self.model_combo = QComboBox()
        for label, value in _MODELS:
            self.model_combo.addItem(label, userData=value)
        self.turns_spin = QSpinBox()
        self.turns_spin.setRange(2, 100)
        form.addRow("LLM 모델", self.model_combo)
        form.addRow("최대 턴 수", self.turns_spin)
        lay.addLayout(form)

        note = QLabel("※ 종량 과금 API key 방식은 지원하지 않습니다 — 이 도구는 Claude Code "
                      "구독 연동 전용이며, ANTHROPIC_API_KEY가 설정돼 있으면 실행을 거부합니다.")
        note.setWordWrap(True)
        lay.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._load()
        self._refresh()

    def _load(self) -> None:
        s = AppSettings.load(self.root)
        idx = next((i for i, (_, v) in enumerate(_MODELS) if v == s.model), 0)
        self.model_combo.setCurrentIndex(idx)
        self.turns_spin.setValue(s.max_turns)

    def _refresh(self) -> None:
        s = claude_status()
        if s["api_key_present"]:
            self.account_label.setText("⚠ ANTHROPIC_API_KEY 감지 — 과금 방지 가드로 LLM 기능 차단 중. "
                                       "환경변수를 해제한 뒤 앱을 재시작하세요.")
        elif s["email"]:
            org = f" · {s['org']}" if s["org"] else ""
            self.account_label.setText(f"현재 연결 계정: {s['email']}{org} (Claude Code 구독 인증)")
        else:
            self.account_label.setText("로그인 정보 없음 — 아래 버튼으로 터미널을 열어 로그인하세요.")

    def _open_terminal(self) -> None:
        cli = shutil.which("claude")
        if not cli:
            self.account_label.setText("claude CLI를 PATH에서 찾지 못했습니다 — Claude Code 설치 후 "
                                       "다시 시도하세요 (https://claude.com/claude-code)")
            return
        # 새 콘솔 창에서 claude 실행 — 사용자가 /login·/logout 수행
        subprocess.Popen(["cmd", "/c", "start", "Claude Login", "cmd", "/k", "claude"],
                         shell=False)

    def _save(self) -> None:
        AppSettings(model=self.model_combo.currentData(),
                    max_turns=self.turns_spin.value()).save(self.root)
        self.accept()
