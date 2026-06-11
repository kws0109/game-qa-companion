import json
from pathlib import Path

from companion.analysis.qa import ask
from companion.providers.base import FakeProvider
from companion.session import Manifest


def _session_with_analysis(tmp_path: Path) -> Path:
    d = tmp_path / "s"
    (d / "frames").mkdir(parents=True)
    m = Manifest(game="G", source="adb", started_at="t", interval=2.0)
    m.add_frame("frames/frame_000000.png", 0.0)
    m.save(d)
    (d / "analysis.json").write_text(json.dumps(
        {"game": "G", "source": "adb", "started_at": "t", "frame_count": 1,
         "candidates": [{"signal": {"kind": "stall", "start_t": 10.0, "end_t": 30.0},
                         "evidence": ["frames/frame_000000.png"],
                         "llm": {"verdict": "defect_candidate", "severity": "low",
                                 "explanation": "정체"}}]},
        ensure_ascii=False), encoding="utf-8")
    return d


def test_ask_includes_context_and_question(tmp_path):
    d = _session_with_analysis(tmp_path)
    p = FakeProvider(responses=["10초~30초 구간에 정체 후보가 있었습니다."])
    answer = ask(d, "정체 구간 있었어?", p)
    assert "정체" in answer
    sent = p.calls[0]["prompt"]
    assert "정체 구간 있었어?" in sent
    assert "stall" in sent  # analysis.json 컨텍스트 포함
