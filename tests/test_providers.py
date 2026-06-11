from pathlib import Path

from companion.providers.base import FakeProvider


def test_fake_provider_returns_scripted_responses():
    p = FakeProvider(responses=['{"verdict":"defect_candidate"}', "second"])
    assert p.run("prompt1") == '{"verdict":"defect_candidate"}'
    assert p.run("prompt2", images=[Path("a.png")]) == "second"
    assert p.calls[0]["prompt"] == "prompt1"
    assert p.calls[1]["images"] == [Path("a.png")]


def test_fake_provider_repeats_last_response():
    p = FakeProvider(responses=["only"])
    p.run("a")
    assert p.run("b") == "only"
