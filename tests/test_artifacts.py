import os
import time
from pathlib import Path

import pytest

from companion.capture.artifacts import import_artifacts
from companion.session import Manifest


def test_import_builds_standard_session(tmp_path: Path, make_png):
    src = tmp_path / "qa_automation_out"
    src.mkdir()
    for i in range(3):
        f = src / f"step_{i:03d}.png"
        f.write_bytes(make_png((i * 40, 0, 0)))
        ts = time.time() - (3 - i) * 2
        os.utime(f, (ts, ts))
    out = import_artifacts(src, tmp_path / "sessions", game="Blue Archive")
    m = Manifest.load(out)
    assert m.source == "qa_automation_artifacts"
    assert len(m.frames) == 3
    assert m.frames[0].t == 0.0
    assert m.frames[1].t > m.frames[0].t
    assert (out / m.frames[0].file).exists()


def test_import_empty_dir_raises(tmp_path: Path):
    src = tmp_path / "empty"
    src.mkdir()
    with pytest.raises(ValueError, match="no screenshots"):
        import_artifacts(src, tmp_path / "sessions", game="G")
