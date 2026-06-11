import json
from pathlib import Path

from companion.analysis.pipeline import analyze_session
from companion.config import GameConfig
from companion.providers.base import FakeProvider
from companion.session import Manifest


def _stall_session(tmp_path: Path, make_png) -> Path:
    d = tmp_path / "s"
    (d / "frames").mkdir(parents=True)
    m = Manifest(game="G", source="fake", started_at="2026-06-12T00:00:00", interval=2.0)
    frozen = make_png((30, 30, 30))
    pngs = [make_png((50, 0, 0)), make_png((120, 0, 0))] + [frozen] * 5 + [make_png((0, 90, 0))]
    for i, b in enumerate(pngs):
        name = f"frames/frame_{i:06d}.png"
        (d / name).write_bytes(b)
        m.add_frame(name, i * 2.0)
    m.save(d)
    return d


def _cfg() -> GameConfig:
    return GameConfig(name="G", type="idle",
                      analysis_prompts={"detect_anomaly": "이상 여부를 판단하라."})


def test_analyze_writes_candidates_with_evidence(tmp_path, make_png):
    d = _stall_session(tmp_path, make_png)
    provider = FakeProvider(responses=[json.dumps(
        {"verdict": "defect_candidate", "severity": "medium",
         "explanation": "화면이 10초간 변화 없음 — 진행 정체 의심"})])
    result = analyze_session(d, _cfg(), provider)
    assert len(result["candidates"]) == 1
    c = result["candidates"][0]
    assert c["signal"]["kind"] == "stall"
    assert c["llm"]["verdict"] == "defect_candidate"
    assert len(c["evidence"]) == 3 and all(e.startswith("frames/") for e in c["evidence"])
    assert (Path(d) / "analysis.json").exists()
    # 프롬프트에 근거 요구가 들어갔는지 + 이미지가 첨부됐는지
    assert "JSON" in provider.calls[0]["prompt"]
    assert len(provider.calls[0]["images"]) == 3


def test_analyze_no_signal_no_llm_call(tmp_path, make_png):
    d = tmp_path / "s2"
    (d / "frames").mkdir(parents=True)
    m = Manifest(game="G", source="fake", started_at="t", interval=2.0)
    for i in range(4):
        name = f"frames/frame_{i:06d}.png"
        (d / name).write_bytes(make_png((i * 60 % 255, i * 30 % 255, 0)))
        m.add_frame(name, i * 2.0)
    m.save(d)
    provider = FakeProvider(responses=["unused"])
    result = analyze_session(d, _cfg(), provider)
    assert result["candidates"] == [] and provider.calls == []


def test_analyze_tolerates_non_json_llm_output(tmp_path, make_png):
    d = _stall_session(tmp_path, make_png)
    provider = FakeProvider(responses=["판단: 문제 없어 보임 (JSON 아님)"])
    result = analyze_session(d, _cfg(), provider)
    c = result["candidates"][0]
    assert c["llm"]["verdict"] == "unparsed"
    assert "JSON 아님" in c["llm"]["raw"]
