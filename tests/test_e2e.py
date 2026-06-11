import os
import re
import time
from pathlib import Path

from companion.cli import main


def test_e2e_import_analyze_report(tmp_path: Path, make_png, capsys):
    # 1) 가짜 산출물: 변화 2장 → 동결 5장 → 변화 1장 (stall 신호 유도)
    src = tmp_path / "artifacts"
    src.mkdir()
    frozen = make_png((30, 30, 30))
    pngs = [make_png((60, 0, 0)), make_png((140, 0, 0))] + [frozen] * 5 + [make_png((0, 120, 0))]
    base = time.time() - 100
    for i, b in enumerate(pngs):
        f = src / f"shot_{i:03d}.png"
        f.write_bytes(b)
        os.utime(f, (base + i * 2, base + i * 2))

    cfg = tmp_path / "game.yaml"
    cfg.write_text('name: "E2E Game"\ntype: "idle"\n', encoding="utf-8")

    # 2) import
    main(["import-artifacts", "--src", str(src), "--game-name", "E2E Game",
          "--out", str(tmp_path / "sessions")])
    out = capsys.readouterr().out
    session = Path(re.search(r"session saved: (.+)", out).group(1).strip())
    assert session.exists()

    # 3) analyze (fake provider — LLM 호출 없음)
    main(["analyze", "--session", str(session), "--game", str(cfg), "--provider", "fake"])
    out = capsys.readouterr().out
    assert "candidates: 1" in out

    report = (session / "report.md").read_text(encoding="utf-8")
    assert "E2E Game" in report and "stall" in report and "사람 검수" in report
