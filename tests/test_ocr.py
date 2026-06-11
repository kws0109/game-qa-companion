import pytest

from companion.vision.ocr import find_jumps, parse_number


def test_parse_number():
    assert parse_number("HP 1,234") == 1234.0
    assert parse_number("Lv.57") == 57.0
    assert parse_number("---") is None


def test_find_jumps_detects_drop():
    series = [(0.0, 1000.0), (2.0, 990.0), (4.0, 120.0), (6.0, 118.0)]
    jumps = find_jumps(series, region_id="hp", rel_threshold=0.5)
    assert len(jumps) == 1
    assert jumps[0]["t"] == 4.0 and jumps[0]["region_id"] == "hp"


def test_find_jumps_ignores_none():
    series = [(0.0, 100.0), (2.0, None), (4.0, 95.0)]
    assert find_jumps(series, region_id="x") == []


def test_ocr_engine_requires_paddle():
    pytest.importorskip("paddleocr")  # 미설치 환경에서는 skip
    from companion.vision.ocr import OcrEngine
    assert OcrEngine() is not None
