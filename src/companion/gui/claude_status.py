from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from companion.gui.workers import FuncWorker


def claude_status(home: str | Path | None = None) -> dict:
    """Claude Code 구독 연결 상태 — 로컬 설정만 읽는다 (토큰·시크릿 미접근).

    account는 ~/.claude.json 의 oauthAccount 메타데이터에서 가져온다.
    """
    home = Path(home or Path.home())
    out = {
        "cli": shutil.which("claude"),
        "api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "email": None,
        "org": None,
    }
    cfg = home / ".claude.json"
    if cfg.exists():
        try:
            account = json.loads(cfg.read_text(encoding="utf-8")).get("oauthAccount") or {}
            out["email"] = account.get("emailAddress")
            out["org"] = account.get("organizationName")
        except (json.JSONDecodeError, OSError):
            pass
    return out


def _ping() -> str:
    from companion.providers.claude_agent import ClaudeAgentProvider
    t0 = time.monotonic()
    answer = ClaudeAgentProvider(max_turns=2).run("연결 상태 확인이다. 'OK' 한 단어로만 답하라.")
    dt = time.monotonic() - t0
    return f"{(answer or '(빈 응답)').strip()[:30]} ({dt:.1f}초)"


class ClaudeStatusWidget(QWidget):
    """상태바용 — 연결 계정·상태 점등 + 실호출 테스트 + 설정."""

    def __init__(self, root: Path | None = None):
        super().__init__()
        self.root = Path(root or Path.cwd())
        self._worker: FuncWorker | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        self.dot = QLabel("●")
        self.text = QLabel("")
        self.test_btn = QPushButton("연결 테스트")
        self.test_btn.setToolTip("Claude를 1회 실호출해 연결을 확인합니다 — 구독 사용량을 소모합니다")
        self.test_btn.clicked.connect(self._test)
        self.settings_btn = QPushButton("설정…")
        self.settings_btn.clicked.connect(self._open_settings)
        lay.addWidget(self.dot)
        lay.addWidget(self.text)
        lay.addWidget(self.test_btn)
        lay.addWidget(self.settings_btn)
        self.refresh()

    def _open_settings(self) -> None:
        from companion.gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.root, self)
        run_dialog = dlg.exec  # Qt 모달 루프
        run_dialog()
        self.refresh()

    def refresh(self) -> None:
        s = claude_status()
        if s["api_key_present"]:
            self._set("#e5a000", "ANTHROPIC_API_KEY 감지 — 과금 방지 가드로 LLM 기능이 차단됩니다. "
                                 "환경변수를 해제하세요")
            return
        if s["email"]:
            org = f" · {s['org']}" if s["org"] else ""
            cli = "" if s["cli"] else " · CLI는 SDK 번들 사용"
            self._set("#2db84d", f"Claude 구독 연결: {s['email']}{org}{cli}")
        else:
            self._set("#d04040", "Claude Code 로그인 정보 없음 — 터미널에서 `claude` 실행 후 로그인하세요")

    def _set(self, color: str, text: str) -> None:
        self.dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        self.text.setText(text)

    def _test(self) -> None:
        self.test_btn.setEnabled(False)
        self.text.setText(self.text.text().split(" | ")[0] + " | 테스트 중… (수십 초 가능)")
        self._worker = FuncWorker(_ping)
        self._worker.done.connect(self._on_test_done)
        self._worker.failed.connect(self._on_test_failed)
        self._worker.start()

    def _on_test_done(self, result: str) -> None:
        self.test_btn.setEnabled(True)
        self.refresh()
        self.text.setText(self.text.text() + f" | 테스트 응답: {result}")

    def _on_test_failed(self, msg: str) -> None:
        self.test_btn.setEnabled(True)
        self.refresh()
        self.text.setText(self.text.text() + f" | 테스트 실패: {msg}")
