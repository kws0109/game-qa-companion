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
    """PaddleOCR lazy wrapper. 설치 안 됐으면 생성 시 안내 포함 에러."""

    def __init__(self, lang: str = "korean"):
        try:
            from paddleocr import PaddleOCR  # lazy — optional dependency
        except ImportError as e:
            raise RuntimeError(
                "OCR 모듈이 설치되지 않았습니다. 터미널에서 `uv sync --extra ocr` 실행 후 "
                "다시 시도하세요 (PaddleOCR — 용량이 커서 선택 설치입니다).") from e
        try:  # paddleocr 2.x
            self._ocr = PaddleOCR(use_angle_cls=False, lang=lang, show_log=False)
        except (TypeError, ValueError):
            # paddleocr 3.x — show_log 등 제거. enable_mkldnn=False 필수:
            # Windows CPU에서 OneDNN/PIR 추론 버그(fused_conv2d·ConvertPirAttribute) 회피
            self._ocr = PaddleOCR(lang=lang, enable_mkldnn=False)

    def _raw_items(self, img) -> list[tuple[str, list]]:
        """(text, polygon) 목록 — paddleocr 2.x/3.x 양쪽 API 대응."""
        try:  # 2.x: ocr(img, cls=False) → [[ [pts, (text, conf)], ... ]]
            result = self._ocr.ocr(img, cls=False)
            lines = (result[0] or []) if result else []
            return [(item[1][0], item[0]) for item in lines]
        except (TypeError, ValueError, IndexError, KeyError):
            pass
        items: list[tuple[str, list]] = []
        for res in self._ocr.predict(img):  # 3.x: OCRResult dict-like
            texts = res["rec_texts"] or []
            polys = res["rec_polys"]
            items.extend(zip(texts, list(polys)))
        return items

    def read_text(self, png: bytes) -> str:
        img = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        return " ".join(t for t, _ in self._raw_items(img))

    def read_items(self, png: bytes) -> list[tuple[str, tuple[int, int, int, int]]]:
        """텍스트와 bbox(l,t,r,b) 목록 — UI 요소 카탈로그용."""
        img = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
        items = []
        for text, poly in self._raw_items(img):
            xs = [int(p[0]) for p in poly]
            ys = [int(p[1]) for p in poly]
            items.append((text, (min(xs), min(ys), max(xs), max(ys))))
        return items


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
