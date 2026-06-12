from pathlib import Path

import cv2
import numpy as np

from companion.session import Manifest
from companion.vision.elements import detect_boxes, stability_mask


def _noisy_session_with_static_hud(tmp_path: Path, n: int = 10) -> tuple[Path, bytes]:
    """프레임마다 위치가 바뀌는 '월드 오브젝트' 사각형들 + 고정 HUD (40,30)-(160,80)."""
    rng = np.random.default_rng(7)
    d = tmp_path / "s"
    (d / "frames").mkdir(parents=True)
    m = Manifest(game="G", source="fake", started_at="t", interval=2.0)
    last = b""
    for i in range(n):
        img = np.full((300, 500, 3), 90, dtype=np.uint8)
        for _ in range(4):  # 움직이는 월드 오브젝트 — 매 프레임 다른 위치
            x, y = int(rng.integers(0, 380)), int(rng.integers(100, 220))
            cv2.rectangle(img, (x, y), (x + 80, y + 60),
                          tuple(int(v) for v in rng.integers(120, 255, 3)), -1)
        cv2.rectangle(img, (40, 30), (160, 80), (240, 240, 240), -1)  # 고정 HUD
        ok, buf = cv2.imencode(".png", img)
        last = buf.tobytes()
        name = f"frames/frame_{i:06d}.png"
        (d / name).write_bytes(last)
        m.add_frame(name, i * 2.0)
    m.save(d)
    return d, last


def test_stability_mask_keeps_hud_drops_world_noise(tmp_path):
    session, frame = _noisy_session_with_static_hud(tmp_path)
    mask = stability_mask(session, sample=10, std_threshold=12.0)
    # HUD 중심은 안정(255), 노이즈 영역은 가변(0)
    assert mask[55, 100] == 255
    assert mask[250, 400] == 0

    unfiltered = detect_boxes(frame)
    filtered = detect_boxes(frame, mask=mask)
    assert len(filtered) < len(unfiltered)  # 노이즈 박스가 걸러짐
    assert any(abs(b[0] - 40) <= 4 and abs(b[1] - 30) <= 4 for b in filtered)  # HUD는 생존
