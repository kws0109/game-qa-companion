from __future__ import annotations

import json
from pathlib import Path

from companion.providers.base import LLMProvider

_ASK_TMPL = """당신은 게임 QA 세션 분석 보조다. 아래는 한 세션의 분석 결과 JSON이다.

{analysis}

질문: {question}

분석 결과에 있는 사실만으로 한국어로 간결히 답하라. 결과에 없는 내용은 "분석 데이터에 없음"이라고 답할 것.
필요하면 근거 프레임 파일명을 함께 제시하라."""


def ask(session_dir: str | Path, question: str, provider: LLMProvider) -> str:
    d = Path(session_dir)
    analysis = (d / "analysis.json").read_text(encoding="utf-8")
    return provider.run(_ASK_TMPL.format(analysis=analysis, question=question))
