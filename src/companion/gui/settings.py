from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AppSettings:
    """앱 단위 LLM 연결 설정 — app_settings.json (사용자 로컬, git 미추적)."""

    model: str | None = None  # None = Claude Code 기본 모델
    max_turns: int = 30

    @classmethod
    def load(cls, root: str | Path) -> "AppSettings":
        p = Path(root) / "app_settings.json"
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(model=data.get("model"), max_turns=int(data.get("max_turns", 30)))
        except (json.JSONDecodeError, ValueError, OSError):
            return cls()

    def save(self, root: str | Path) -> None:
        (Path(root) / "app_settings.json").write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
