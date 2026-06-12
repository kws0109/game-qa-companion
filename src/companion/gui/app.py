from __future__ import annotations

import faulthandler
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QMessageBox, QSystemTrayIcon, QTabWidget,
)

from companion.gui.capture_panel import CapturePanel
from companion.gui.inspect_panel import InspectPanel
from companion.gui.library_panel import LibraryPanel
from companion.gui.sessions_panel import SessionsPanel

_ERROR_LOG = "gui_error.log"


def make_icon() -> QIcon:
    """트레이·창 아이콘 — 에셋 파일 없이 코드로 생성."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setBrush(QColor(45, 184, 77))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setPen(QColor(255, 255, 255))
    f = p.font()
    f.setPixelSize(36)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "Q")
    p.end()
    return QIcon(pix)


def install_crash_logging(root: Path) -> Path:
    """미처리 예외·네이티브 크래시를 파일로 — '조용히 사라지는' 종료의 원인 추적용."""
    log_path = root / _ERROR_LOG
    fh = open(log_path, "a", encoding="utf-8")  # noqa: SIM115 — 프로세스 수명 동안 유지
    faulthandler.enable(fh)

    def _hook(exc_type, exc, tb) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        fh.write(f"\n[{stamp}] unhandled exception\n")
        fh.write("".join(traceback.format_exception(exc_type, exc, tb)))
        fh.flush()
        try:
            box = QMessageBox(QMessageBox.Icon.Critical, "Game QA Companion 오류",
                              f"예기치 못한 오류가 발생했습니다.\n{exc}\n\n로그: {log_path}")
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            box.show()  # 비차단 — 크래시 흐름·테스트에서 멈추지 않게
        except Exception:  # GUI가 이미 죽었으면 로그만
            pass

    sys.excepthook = _hook
    return log_path


class MainWindow(QMainWindow):
    def __init__(self, root: str | Path | None = None):
        super().__init__()
        root = Path(root or Path.cwd())
        self.setWindowTitle("Game QA Companion")
        self.setWindowIcon(make_icon())
        self.resize(1280, 800)
        self._really_quit = False

        self.tabs = QTabWidget()
        self.capture = CapturePanel(root)
        self.sessions = SessionsPanel(root)
        self.inspect = InspectPanel(root)
        self.library = LibraryPanel(root)
        self.tabs.addTab(self.capture, "캡처")
        self.tabs.addTab(self.sessions, "세션·분석")
        self.tabs.addTab(self.inspect, "Inspect")
        self.tabs.addTab(self.library, "라이브러리")
        self.tabs.currentChanged.connect(self._on_tab)
        self.setCentralWidget(self.tabs)

        from companion.gui.claude_status import ClaudeStatusWidget
        self.claude_status = ClaudeStatusWidget(root)
        self.statusBar().addPermanentWidget(self.claude_status)

        # 트레이 상주 — 창을 닫아도 프로세스는 살아서 트레이에서 복원 가능
        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(make_icon(), self)
            self.tray.setToolTip("Game QA Companion")
            menu = QMenu()
            menu.addAction("열기", self._restore)
            menu.addAction("종료", self._quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._on_tray)
            self.tray.show()

    def _on_tab(self, idx: int) -> None:
        # 탭 전환 시 목록 동기화 — 캡처 직후 세션이 바로 보이게
        if self.tabs.widget(idx) is self.sessions:
            self.sessions.refresh()
        elif self.tabs.widget(idx) is self.inspect:
            self.inspect.reload_sessions()
        elif self.tabs.widget(idx) is self.library:
            self.library.reload_games()

    # --- tray ----------------------------------------------------------
    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restore()

    def _restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self._really_quit = True
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self.tray is not None and not self._really_quit:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Game QA Companion",
                "트레이로 최소화되었습니다 — 아이콘 클릭으로 다시 열고, 종료는 트레이 메뉴에서.",
                QSystemTrayIcon.MessageIcon.Information, 3000)
        else:
            event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    install_crash_logging(Path.cwd())

    # 중복 실행 방지 — 이미 떠 있으면 안내 후 종료 (창은 트레이에 숨어 있을 수 있음)
    lock = QLockFile(str(Path(tempfile.gettempdir()) / "game-qa-companion.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(
            None, "Game QA Companion",
            "이미 실행 중입니다 — 작업 표시줄 트레이의 초록 Q 아이콘을 클릭해 창을 여세요.")
        return

    w = MainWindow()
    app.setQuitOnLastWindowClosed(w.tray is None)  # 트레이 있으면 창 닫아도 상주
    w.show()
    run_event_loop = app.exec  # Qt 이벤트 루프
    code = run_event_loop()
    del lock
    sys.exit(code)


if __name__ == "__main__":
    main()
