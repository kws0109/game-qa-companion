from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from companion.session import Manifest


def _decode(png: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("invalid png bytes")
    return img


def frame_diff(a: bytes, b: bytes) -> float:
    """두 프레임의 평균 절대 픽셀 차 (0=동일, 255=최대). 해상도 다르면 b를 a에 맞춤."""
    ia, ib = _decode(a), _decode(b)
    if ia.shape != ib.shape:
        ib = cv2.resize(ib, (ia.shape[1], ia.shape[0]))
    return float(np.mean(cv2.absdiff(ia, ib)))


def find_stalls(session_dir: str | Path, *, threshold: float = 2.0,
                min_run: int = 4) -> list[dict]:
    """연속 프레임이 거의 변하지 않는 구간(정체/프리즈 후보)을 찾는다."""
    d = Path(session_dir)
    m = Manifest.load(d)
    stalls: list[dict] = []
    run_start: int | None = None
    prev = None
    for i, fr in enumerate(m.frames):
        cur = (d / fr.file).read_bytes()
        if prev is not None and frame_diff(prev, cur) < threshold:
            if run_start is None:
                run_start = i - 1
        else:
            if run_start is not None and (i - run_start) >= min_run:
                stalls.append(_stall(m, run_start, i - 1))
            run_start = None
        prev = cur
    if run_start is not None and (len(m.frames) - run_start) >= min_run:
        stalls.append(_stall(m, run_start, len(m.frames) - 1))
    return stalls


def _stall(m: Manifest, i0: int, i1: int) -> dict:
    return {"kind": "stall", "start_t": m.frames[i0].t, "end_t": m.frames[i1].t,
            "frame_count": i1 - i0 + 1,
            "frames": [m.frames[i0].file, m.frames[(i0 + i1) // 2].file, m.frames[i1].file]}


def match_template(frame_png: bytes, template_png: bytes,
                   region: tuple[int, int, int, int] | None = None) -> tuple[float, tuple[int, int]]:
    """frame에서 template 최고 일치 위치. region=(l,t,r,b)이면 그 안에서만 탐색."""
    frame, tpl = _decode(frame_png), _decode(template_png)
    off_x = off_y = 0
    if region:
        l, t, r, b = region
        frame = frame[t:b, l:r]
        off_x, off_y = l, t
    res = cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return float(score), (loc[0] + off_x, loc[1] + off_y)
