from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from companion.gui.capture_panel import CapturePanel
from companion.gui.inspect_panel import InspectPanel
from companion.gui.library_panel import LibraryPanel
from companion.gui.sessions_panel import SessionsPanel


class MainWindow(QMainWindow):
    def __init__(self, root: str | Path | None = None):
        super().__init__()
        root = Path(root or Path.cwd())
        self.setWindowTitle("Game QA Companion")
        self.resize(1280, 800)

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

    def _on_tab(self, idx: int) -> None:
        # 탭 전환 시 목록 동기화 — 캡처 직후 세션이 바로 보이게
        if self.tabs.widget(idx) is self.sessions:
            self.sessions.refresh()
        elif self.tabs.widget(idx) is self.inspect:
            self.inspect.reload_sessions()
        elif self.tabs.widget(idx) is self.library:
            self.library.reload_games()


def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    run_event_loop = app.exec  # Qt 이벤트 루프
    sys.exit(run_event_loop())


if __name__ == "__main__":
    main()
