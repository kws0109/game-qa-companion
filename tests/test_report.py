import json
from pathlib import Path

from companion.analysis.report import render_report


def test_render_report(tmp_path: Path):
    analysis = {"game": "Night Crows", "source": "windows", "started_at": "2026-06-12T10:00:00",
                "frame_count": 900,
                "candidates": [{
                    "signal": {"kind": "stall", "start_t": 120.0, "end_t": 150.0, "frame_count": 15},
                    "evidence": ["frames/frame_000060.png", "frames/frame_000067.png",
                                 "frames/frame_000075.png"],
                    "llm": {"verdict": "defect_candidate", "severity": "medium",
                            "explanation": "로딩 아이콘 없이 30초간 화면 정체."}}]}
    (tmp_path / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False),
                                            encoding="utf-8")
    out = render_report(tmp_path)
    text = out.read_text(encoding="utf-8")
    assert out.name == "report.md"
    assert "Night Crows" in text
    assert "defect_candidate" in text and "medium" in text
    assert "![evidence](frames/frame_000060.png)" in text
    assert "사람 검수" in text  # 검증 전제 문구 필수


def test_render_report_empty_candidates(tmp_path: Path):
    (tmp_path / "analysis.json").write_text(json.dumps(
        {"game": "G", "source": "adb", "started_at": "t", "frame_count": 10,
         "candidates": []}, ensure_ascii=False), encoding="utf-8")
    text = render_report(tmp_path).read_text(encoding="utf-8")
    assert "결함 후보가 탐지되지 않았습니다" in text
