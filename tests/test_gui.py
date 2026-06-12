import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 헤드리스 스모크용

from companion.gui.util import list_game_configs, list_sessions


def _fake_session(base: Path, name: str, frames: int = 2) -> None:
    d = base / "sessions" / name
    (d / "frames").mkdir(parents=True)
    records = []
    for i in range(frames):
        f = d / "frames" / f"frame_{i:06d}.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
        records.append({"file": f"frames/frame_{i:06d}.png", "t": i * 2.0})
    (d / "manifest.json").write_text(json.dumps(
        {"game": "G", "source": "fake", "started_at": "t", "interval": 2.0,
         "frames": records}), encoding="utf-8")


def test_list_sessions_summarizes(tmp_path: Path):
    _fake_session(tmp_path, "20260612_000001")
    _fake_session(tmp_path, "20260612_000002", frames=3)
    out = list_sessions(tmp_path)
    assert [s["name"] for s in out] == ["20260612_000002", "20260612_000001"]
    assert out[0]["frames"] == 3 and out[0]["analyzed"] is False


def test_list_game_configs_empty_ok(tmp_path: Path):
    assert list_game_configs(tmp_path) == []


def test_main_window_constructs(tmp_path: Path):
    from PySide6.QtWidgets import QApplication
    from companion.gui.app import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(root=tmp_path)
    assert w.tabs.count() == 4
    assert w.tabs.tabText(3) == "라이브러리"
