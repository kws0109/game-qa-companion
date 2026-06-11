from __future__ import annotations

from pathlib import Path
from typing import Protocol


class LLMProvider(Protocol):
    """이미지 경로 목록 + 프롬프트 → 텍스트 응답. provider 교체 가능."""

    def run(self, prompt: str, images: list[Path] | None = None) -> str: ...


class FakeProvider:
    """테스트용 — 호출 기록 + 스크립트된 응답."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def run(self, prompt: str, images: list[Path] | None = None) -> str:
        self.calls.append({"prompt": prompt, "images": images or []})
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]
