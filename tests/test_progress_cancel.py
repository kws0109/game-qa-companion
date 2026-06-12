import json
from pathlib import Path

import pytest

from companion.analysis.pipeline import analyze_session
from companion.config import GameConfig
from companion.providers.base import FakeProvider
from companion.session import Manifest


def _stall_session(tmp_path: Path, make_png) -> Path:
    d = tmp_path / "s"
    (d / "frames").mkdir(parents=True)
    m = Manifest(game="G", source="fake", started_at="t", interval=2.0)
    frozen = make_png((30, 30, 30))
    pngs = [make_png((50, 0, 0)), make_png((120, 0, 0))] + [frozen] * 5 + [make_png((0, 90, 0))]
    for i, b in enumerate(pngs):
        name = f"frames/frame_{i:06d}.png"
        (d / name).write_bytes(b)
        m.add_frame(name, i * 2.0)
    m.save(d)
    return d


def test_progress_callback_reports_stages(tmp_path, make_png):
    d = _stall_session(tmp_path, make_png)
    events = []
    provider = FakeProvider(responses=[json.dumps(
        {"verdict": "likely_normal", "severity": "low", "explanation": "x"})])
    analyze_session(d, GameConfig(name="G", type="idle"), provider,
                    progress=lambda msg, pct: events.append((msg, pct)))
    assert any("신호 수집" in m for m, _ in events)
    assert any("후보 1/1" in m for m, _ in events)
    assert events[-1][1] == 95  # 저장 단계


def test_cancel_stops_before_llm_calls(tmp_path, make_png):
    d = _stall_session(tmp_path, make_png)
    provider = FakeProvider(responses=["unused"])
    with pytest.raises(RuntimeError, match="중단"):
        analyze_session(d, GameConfig(name="G", type="idle"), provider,
                        cancel=lambda: True)
    assert provider.calls == []  # LLM 호출 전에 멈춤
    assert not (d / "analysis.json").exists()  # 부분 결과 미저장
