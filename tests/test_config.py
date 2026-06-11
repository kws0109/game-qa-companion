from pathlib import Path

import pytest

from companion.config import GameConfig

VALID = """
name: "Example Game"
type: "idle"
capture:
  window_title: "NIGHT CROW"   # 창 제목 부분 일치 — "NIGHT CROW(1)" 같은 suffix 변동 흡수
  adb_serial: null
templates:
  - id: "play_button"
    image: "templates/example/play_button.png"
    region: [800, 1500, 1000, 1700]
ocr_regions:
  - id: "stage"
    region: [50, 100, 300, 150]
    numeric: true
analysis_prompts:
  detect_anomaly: "이 게임 세션에서 이상 징후를 분석하라."
"""


def test_load_valid_config(tmp_path: Path):
    p = tmp_path / "game.yaml"
    p.write_text(VALID, encoding="utf-8")
    cfg = GameConfig.load(p)
    assert cfg.name == "Example Game"
    assert cfg.templates[0].id == "play_button"
    assert cfg.templates[0].region == (800, 1500, 1000, 1700)
    assert cfg.ocr_regions[0].numeric is True
    assert "detect_anomaly" in cfg.analysis_prompts
    assert cfg.capture_window_title == "NIGHT CROW"
    assert cfg.capture_adb_serial is None


def test_missing_name_raises(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("type: idle", encoding="utf-8")
    with pytest.raises(ValueError, match="name"):
        GameConfig.load(p)


def test_ocr_region_optional(tmp_path: Path):
    p = tmp_path / "min.yaml"
    p.write_text('name: "G"\ntype: "idle"\n', encoding="utf-8")
    cfg = GameConfig.load(p)
    assert cfg.templates == [] and cfg.ocr_regions == []
    assert cfg.capture_window_title is None  # capture 섹션 자체가 선택
