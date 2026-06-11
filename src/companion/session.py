from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol


class Grabber(Protocol):
    def grab(self) -> bytes: ...


@dataclass
class FrameRecord:
    file: str
    t: float  # 세션 시작 기준 상대 초


@dataclass
class Manifest:
    game: str
    source: str
    started_at: str
    interval: float
    frames: list[FrameRecord] = field(default_factory=list)

    def add_frame(self, file: str, t: float) -> None:
        self.frames.append(FrameRecord(file=file, t=t))

    def save(self, session_dir: str | Path) -> None:
        p = Path(session_dir) / "manifest.json"
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                     encoding="utf-8")

    @classmethod
    def load(cls, session_dir: str | Path) -> "Manifest":
        data = json.loads((Path(session_dir) / "manifest.json").read_text(encoding="utf-8"))
        frames = [FrameRecord(**f) for f in data.pop("frames", [])]
        return cls(frames=frames, **data)


def record_session(grabber: Grabber, base_dir: str | Path, *, game: str, source: str,
                   interval: float, max_frames: int | None = None,
                   duration: float | None = None) -> Path:
    """interval 간격으로 grab → PNG 저장. 매 프레임마다 manifest 저장(중단 안전).

    stateless 원칙: grabber 호출 간 상태 없음. 한 번의 grab 실패는 건너뛰고 계속.
    """
    started = datetime.now()
    session_dir = Path(base_dir) / started.strftime("%Y%m%d_%H%M%S")
    frames_dir = session_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(game=game, source=source,
                        started_at=started.isoformat(timespec="seconds"),
                        interval=interval)
    t0 = time.monotonic()
    i = 0
    while True:
        if max_frames is not None and i >= max_frames:
            break
        now = time.monotonic() - t0
        if duration is not None and now >= duration:
            break
        try:
            png = grabber.grab()
        except Exception as e:  # 한 프레임 실패가 세션을 죽이지 않게
            print(f"[warn] grab failed at t={now:.1f}s: {e}")
            time.sleep(interval)
            continue
        name = f"frames/frame_{i:06d}.png"
        (session_dir / name).write_bytes(png)
        manifest.add_frame(name, round(now, 3))
        manifest.save(session_dir)
        i += 1
        time.sleep(max(0.0, interval - ((time.monotonic() - t0) - now)))
    return session_dir
