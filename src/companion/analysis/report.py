from __future__ import annotations

import json
from pathlib import Path


def render_report(session_dir: str | Path) -> Path:
    d = Path(session_dir)
    a = json.loads((d / "analysis.json").read_text(encoding="utf-8"))
    lines = [
        f"# QA 분석 리포트 — {a['game']}",
        "",
        f"- 입력 소스: `{a['source']}` · 시작: {a['started_at']} · 프레임 {a['frame_count']}장",
        f"- 결함 후보: {len(a['candidates'])}건",
        "",
    ]
    if not a["candidates"]:
        lines.append("결함 후보가 탐지되지 않았습니다.")
    for i, c in enumerate(a["candidates"], 1):
        sig, llm = c["signal"], c["llm"]
        lines += [
            f"## 후보 {i} — {sig['kind']} · 판정: {llm['verdict']} · 심각도: {llm['severity']}",
            "",
            f"**신호**: `{json.dumps(sig, ensure_ascii=False)}`",
            "",
            f"**LLM 판단**: {llm['explanation'] or llm.get('raw', '')}",
            "",
            "**근거 스크린샷**:",
            "",
        ]
        lines += [f"![evidence]({e})" for e in c["evidence"]]
        lines.append("")
    lines += ["---",
              "> 본 리포트는 LLM 보조 분석 결과입니다. 결함 확정·심각도·제출 여부는 "
              "**사람 검수**를 거쳐야 합니다."]
    out = d / "report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
