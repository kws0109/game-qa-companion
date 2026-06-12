from __future__ import annotations

import json
import re
from pathlib import Path

from companion.config import GameConfig
from companion.providers.base import LLMProvider
from companion.session import Manifest
from companion.vision.analyzer import find_stalls

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

_PROMPT_TMPL = """당신은 게임 QA 분석 보조다. 아래 신호와 스크린샷을 보고 결함 후보인지 판단하라.

게임: {game}
분석 지침: {game_prompt}
탐지된 신호: {signal}

반드시 아래 JSON 형식으로만 답하라:
{{"verdict": "defect_candidate" 또는 "likely_normal", "severity": "low|medium|high", "explanation": "판단 근거 (한국어, 2문장 이내)"}}

주의: 확신이 없으면 likely_normal. 스크린샷에서 직접 확인되는 것만 근거로 쓸 것."""


def _parse_llm(raw: str) -> dict:
    m = _JSON_BLOCK.search(raw)
    if m:
        try:
            data = json.loads(m.group())
            if "verdict" in data:
                return {"verdict": data["verdict"],
                        "severity": data.get("severity", "low"),
                        "explanation": data.get("explanation", ""), "raw": raw}
        except json.JSONDecodeError:
            pass
    return {"verdict": "unparsed", "severity": "low", "explanation": "", "raw": raw}


def collect_signals(session_dir: str | Path, config: GameConfig,
                    ocr_engine=None) -> list[dict]:
    """룰 기반 1차 필터 — LLM 호출 전에 후보를 좁힌다 (비용·오탐 통제)."""
    signals = list(find_stalls(session_dir))
    if ocr_engine is not None and config.ocr_regions:
        from companion.vision.ocr import find_jumps, numeric_series
        d = Path(session_dir)
        m = Manifest.load(d)
        for region in config.ocr_regions:
            if not region.numeric:
                continue
            series = numeric_series(d, region, ocr_engine)
            for j in find_jumps(series, region_id=region.id):
                idx = min(range(len(m.frames)), key=lambda i: abs(m.frames[i].t - j["t"]))
                j["frames"] = [m.frames[max(0, idx - 1)].file, m.frames[idx].file,
                               m.frames[min(len(m.frames) - 1, idx + 1)].file]
                signals.append(j)
    return signals


def analyze_session(session_dir: str | Path, config: GameConfig,
                    provider: LLMProvider, ocr_engine=None,
                    max_candidates: int = 10,
                    progress=None, cancel=None) -> dict:
    """max_candidates: LLM 호출 비용 상한 — 신호가 넘치면 지속 시간이 긴 것부터 상위 N건만 판정.

    progress(msg, pct)·cancel() 은 선택 — GUI가 진행 표시·협조적 취소에 사용.
    """
    def _p(msg: str, pct: int = -1) -> None:
        if progress:
            progress(msg, pct)

    def _check_cancel() -> None:
        if cancel and cancel():
            raise RuntimeError("사용자가 분석을 중단했습니다")

    d = Path(session_dir)
    m = Manifest.load(d)
    game_prompt = config.analysis_prompts.get("detect_anomaly", "이상 징후를 판단하라.")
    _p("신호 수집 중 (룰 기반 1차 필터" + (" + OCR 시계열" if ocr_engine else "") + ")…", 10)
    signals = collect_signals(d, config, ocr_engine)
    _check_cancel()
    if len(signals) > max_candidates:
        signals.sort(key=lambda s: s.get("end_t", s.get("t", 0)) - s.get("start_t", s.get("t", 0)),
                     reverse=True)
        print(f"[info] {len(signals)} signals found - judging top {max_candidates} by duration")
        signals = signals[:max_candidates]
    candidates = []
    for i, sig in enumerate(signals, 1):
        _check_cancel()
        _p(f"후보 {i}/{len(signals)} LLM 판정 중… (호출 중에는 완료 후 중단됨)",
           20 + int(70 * (i - 1) / max(1, len(signals))))
        evidence = sig.pop("frames")
        prompt = _PROMPT_TMPL.format(game=m.game, game_prompt=game_prompt,
                                     signal=json.dumps(sig, ensure_ascii=False))
        raw = provider.run(prompt, images=[d / e for e in evidence])
        candidates.append({"signal": sig, "evidence": evidence, "llm": _parse_llm(raw)})
    _p("결과 저장 중…", 95)
    result = {"game": m.game, "source": m.source, "started_at": m.started_at,
              "frame_count": len(m.frames), "candidates": candidates}
    (d / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    return result
