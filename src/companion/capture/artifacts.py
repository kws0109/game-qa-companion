from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from companion.session import Manifest


def import_artifacts(src_dir: str | Path, base_dir: str | Path, *, game: str) -> Path:
    """기존 자동화 플랫폼(QA_Automation 등)의 세션 산출물을 표준 세션 포맷으로 변환.

    원본 repo·산출물은 읽기만 한다. 스크린샷을 복사하고 mtime 기반 상대 시각을 기록.
    """
    src = Path(src_dir)
    shots = sorted([p for p in src.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")],
                   key=lambda p: p.stat().st_mtime)
    if not shots:
        raise ValueError(f"no screenshots found in {src}")
    session_dir = Path(base_dir) / ("import_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    frames_dir = session_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    t0 = shots[0].stat().st_mtime
    manifest = Manifest(game=game, source="qa_automation_artifacts",
                        started_at=datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
                        interval=0.0)
    for i, shot in enumerate(shots):
        name = f"frames/frame_{i:06d}.png"
        shutil.copyfile(shot, session_dir / name)
        manifest.add_frame(name, round(shot.stat().st_mtime - t0, 3))
    manifest.save(session_dir)
    return session_dir
