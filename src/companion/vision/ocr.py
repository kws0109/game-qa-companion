from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from companion.config import OcrRegion
from companion.session import Manifest

_NUM = re.compile(r"\d[\d,\.]*")


def parse_number(text: str) -> float | None:
    m = _NUM.search(text)
    if not m:
        return None
    try:
        return float(m.group().replace(",", "").rstrip("."))
    except ValueError:
        return None


class OcrEngine:
    """PaddleOCR lazy wrapper. 설치 안 됐으면 생성 시 ImportError."""

    def __init__(self, lang: str = "korean"):
        from paddleocr import PaddleOCR  # lazy — optional dependency
        self._ocr = PaddleOCR(use_angle_cls=False, lang=lang, show_log=False)

    def read_text(self, png: bytes) -> str:
        img = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        result = self._ocr.ocr(img, cls=False)
        lines = result[0] or [] if result else []
        return " ".join(item[1][0] for item in lines)


def crop(png: bytes, region: tuple[int, int, int, int]) -> bytes:
    img = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    l, t, r, b = region
    ok, buf = cv2.imencode(".png", img[t:b, l:r])
    return buf.tobytes()


def numeric_series(session_dir: str | Path, ocr_region: OcrRegion,
                   engine: OcrEngine, *, every: int = 1) -> list[tuple[float, float | None]]:
    d = Path(session_dir)
    m = Manifest.load(d)
    out: list[tuple[float, float | None]] = []
    for fr in m.frames[::every]:
        png = crop((d / fr.file).read_bytes(), ocr_region.region)
        out.append((fr.t, parse_number(engine.read_text(png))))
    return out


def find_jumps(series: list[tuple[float, float | None]], *, region_id: str,
               rel_threshold: float = 0.5) -> list[dict]:
    """이웃 샘플 간 상대 변화가 threshold를 넘는 지점 — 수치 급변 후보."""
    jumps: list[dict] = []
    prev_v: float | None = None
    for t, v in series:
        if v is not None and prev_v is not None and prev_v != 0:
            if abs(v - prev_v) / abs(prev_v) >= rel_threshold:
                jumps.append({"kind": "value_jump", "region_id": region_id,
                              "t": t, "from": prev_v, "to": v})
        if v is not None:
            prev_v = v
    return jumps
