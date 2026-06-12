from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal


class FuncWorker(QThread):
    """블로킹 함수를 워커 스레드에서 실행 — UI 멈춤 방지. LLM 호출·분석용.

    with_progress=True면 함수에 progress(msg, pct)·cancel() 키워드를 주입한다.
    pct: 0~100 = 진행률, -1 = 길이를 모르는 단계(무한 바).
    cancel은 협조적 취소 — 함수가 단계 사이에서 직접 확인해야 한다.
    """

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int)

    def __init__(self, fn, *args, with_progress: bool = False, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self._with_progress = with_progress
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # QThread entry
        kwargs = dict(self._kwargs)
        if self._with_progress:
            kwargs["progress"] = lambda msg, pct=-1: self.progress.emit(msg, int(pct))
            kwargs["cancel"] = self._cancel.is_set
        try:
            self.done.emit(self._fn(*self._args, **kwargs))
        except Exception as e:  # GUI에는 메시지로만 — 스레드에서 예외 전파 금지
            self.failed.emit(f"{type(e).__name__}: {e}")
