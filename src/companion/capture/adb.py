from __future__ import annotations

import subprocess


class AdbCapture:
    """`adb exec-out screencap -p` 기반 캡처. 데몬·세션 없음 — 매 호출 독립(stateless).

    ADB 연결이 끊겨도 다음 grab은 새 프로세스라 자동 복구된다. 입력 주입 없음.
    """

    def __init__(self, serial: str | None = None, timeout: float = 10.0):
        self.serial = serial
        self.timeout = timeout

    def _cmd(self) -> list[str]:
        base = ["adb"]
        if self.serial:
            base += ["-s", self.serial]
        return base + ["exec-out", "screencap", "-p"]

    def grab(self) -> bytes:
        out = subprocess.run(self._cmd(), capture_output=True, timeout=self.timeout)
        if out.returncode != 0 or not out.stdout.startswith(b"\x89PNG"):
            raise RuntimeError(f"adb screencap failed: {out.stderr[:200]!r}")
        return out.stdout
