from pathlib import Path

from companion.analysis.pipeline import analyze_session
from companion.config import GameConfig
from companion.providers.base import FakeProvider
from companion.session import Manifest


def test_max_candidates_caps_llm_calls_keeping_longest(tmp_path: Path, make_png):
    """정체 2건(짧은 것·긴 것) → max_candidates=1이면 긴 것만 LLM 판정."""
    d = tmp_path / "s"
    (d / "frames").mkdir(parents=True)
    m = Manifest(game="G", source="fake", started_at="t", interval=2.0)
    frozen_a, frozen_b = make_png((30, 30, 30)), make_png((90, 90, 90))
    moving = [make_png((i * 35 % 255, 0, 0)) for i in range(3)]
    # 짧은 정체(5프레임) → 변화 3 → 긴 정체(8프레임)
    pngs = [frozen_a] * 5 + moving + [frozen_b] * 8
    for i, b in enumerate(pngs):
        name = f"frames/frame_{i:06d}.png"
        (d / name).write_bytes(b)
        m.add_frame(name, i * 2.0)
    m.save(d)
    provider = FakeProvider(responses=[
        '{"verdict":"defect_candidate","severity":"low","explanation":"x"}'])
    result = analyze_session(d, GameConfig(name="G", type="idle"), provider,
                             max_candidates=1)
    assert len(provider.calls) == 1  # LLM 호출 1건으로 제한
    c = result["candidates"][0]["signal"]
    assert (c["end_t"] - c["start_t"]) >= 14.0  # 더 긴 정체가 선택됨
