from __future__ import annotations

import os
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, query


class ClaudeAgentProvider:
    """Claude Agent SDK provider — Claude Code 구독 인증 사용 (별도 API key 불필요).

    이미지는 절대경로를 프롬프트에 나열하고 Read 도구로 읽게 한다.
    비용 가드: ANTHROPIC_API_KEY가 설정돼 있으면 SDK가 종량 과금 API로 붙을 수 있어
    명시적으로 거부한다 (이 도구는 구독 연동 전용).
    """

    def __init__(self, model: str | None = None, max_turns: int = 30):
        if os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY가 설정되어 있습니다. 이 도구는 Claude Code 구독 연동 전용입니다 — "
                "종량 과금을 막기 위해 환경변수를 해제하고 다시 실행하세요.")
        self.model = model
        self.max_turns = max_turns

    def run(self, prompt: str, images: list[Path] | None = None) -> str:
        full = prompt
        if images:
            listed = "\n".join(f"- {Path(p).resolve()}" for p in images)
            full = f"{prompt}\n\n다음 스크린샷 파일들을 Read 도구로 읽고 분석하라:\n{listed}"
        return anyio.run(self._query, full)

    async def _query(self, prompt: str) -> str:
        opts = ClaudeAgentOptions(allowed_tools=["Read"], max_turns=self.max_turns,
                                  model=self.model)
        result_text = ""
        async for message in query(prompt=prompt, options=opts):
            if type(message).__name__ == "ResultMessage":
                result_text = getattr(message, "result", None) or ""
        return result_text
