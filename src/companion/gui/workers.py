from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class FuncWorker(QThread):
    """블로킹 함수를 워커 스레드에서 실행 — UI 멈춤 방지. LLM 호출·분석용."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run(self) -> None:  # QThread entry
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:  # GUI에는 메시지로만 — 스레드에서 예외 전파 금지
            self.failed.emit(f"{type(e).__name__}: {e}")
