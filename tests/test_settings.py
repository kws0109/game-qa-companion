from pathlib import Path

from companion.gui.settings import AppSettings


def test_defaults_when_missing(tmp_path: Path):
    s = AppSettings.load(tmp_path)
    assert s.model is None and s.max_turns == 30


def test_roundtrip(tmp_path: Path):
    AppSettings(model="sonnet", max_turns=50).save(tmp_path)
    s = AppSettings.load(tmp_path)
    assert s.model == "sonnet" and s.max_turns == 50


def test_corrupt_file_falls_back(tmp_path: Path):
    (tmp_path / "app_settings.json").write_text("{broken", encoding="utf-8")
    assert AppSettings.load(tmp_path).max_turns == 30
