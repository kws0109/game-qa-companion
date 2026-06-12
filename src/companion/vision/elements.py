from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from companion.providers.base import LLMProvider

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class UIElement:
    id: int
    kind: str  # CV 단계: "box" | "text" — LLM 라벨링 후: button/icon/gauge/panel 등
    label: str
    bbox: tuple[int, int, int, int]  # (l, t, r, b)
    center: tuple[int, int]


def _decode(png: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("invalid png bytes")
    return img


def _iou(a: tuple, b: tuple) -> float:
    il, it = max(a[0], b[0]), max(a[1], b[1])
    ir, ib = min(a[2], b[2]), min(a[3], b[3])
    if ir <= il or ib <= it:
        return 0.0
    inter = (ir - il) * (ib - it)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / float(min(area_a, area_b))  # 포함 관계도 잡도록 min 기준


def detect_boxes(png: bytes, *, min_side: int = 24,
                 max_area_ratio: float = 0.3) -> list[tuple[int, int, int, int]]:
    """엣지 기반 사각 UI 요소 후보 검출. 게임 화면의 버튼·패널류를 잡는 휴리스틱."""
    img = _decode(png)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cand = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < min_side or bh < min_side:
            continue
        if bw * bh > max_area_ratio * w * h:
            continue
        cand.append((x, y, x + bw, y + bh))
    kept: list[tuple] = []
    for b in sorted(cand, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        if all(_iou(b, k) < 0.6 for k in kept):
            kept.append(b)
    kept.sort(key=lambda b: (b[1], b[0]))  # 좌상단 순 — id 안정성
    return kept


def detect_elements(png: bytes, ocr_engine=None) -> list[UIElement]:
    """CV 박스 + (선택) OCR 텍스트를 합쳐 요소 카탈로그 생성. 전부 로컬 — 비용 0."""
    elements: list[UIElement] = []
    boxes = detect_boxes(png)
    texts: list[tuple[str, tuple]] = []
    if ocr_engine is not None:
        texts = ocr_engine.read_items(png)
    for l, t, r, b in boxes:
        label = ""
        for txt, (tl, tt, tr, tb) in texts:
            if tl >= l and tt >= t and tr <= r and tb <= b:  # 박스 안 텍스트 = 라벨
                label = txt
                break
        elements.append(UIElement(0, "box", label, (l, t, r, b),
                                  ((l + r) // 2, (t + b) // 2)))
    for txt, (tl, tt, tr, tb) in texts:
        inside_any = any(tl >= e.bbox[0] and tt >= e.bbox[1] and tr <= e.bbox[2]
                         and tb <= e.bbox[3] for e in elements)
        if not inside_any:
            elements.append(UIElement(0, "text", txt, (tl, tt, tr, tb),
                                      ((tl + tr) // 2, (tt + tb) // 2)))
    elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))
    for i, e in enumerate(elements, 1):
        e.id = i
    return elements


def render_overlay(png: bytes, elements: list[UIElement]) -> bytes:
    """요소 bbox + id 번호를 그린 주석 이미지 — 스크립트 작성자가 보는 지도."""
    img = _decode(png)
    for e in elements:
        l, t, r, b = e.bbox
        cv2.rectangle(img, (l, t), (r, b), (0, 255, 0), 2)
        tag = f"{e.id}"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img, (l, t - th - 8), (l + tw + 8, t), (0, 255, 0), -1)
        cv2.putText(img, tag, (l + 4, t - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 0), 2)
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


_LABEL_PROMPT = """다음은 게임 화면에서 자동 검출된 UI 요소 목록이다. 주석 이미지의 초록 번호와 대응한다.

{elements}

주석 이미지를 Read 도구로 읽고, 각 요소의 역할과 이름을 판단해 아래 JSON으로만 답하라:
{{"elements": [{{"id": 1, "role": "button|icon|gauge|text|panel|minimap|unknown", "name": "짧은 한국어 이름"}}]}}

규칙: 좌표·id는 절대 수정하지 말 것. 화면에서 식별 불가능한 요소는 role을 unknown으로."""


def label_elements(elements: list[UIElement], annotated_path: Path,
                   provider: LLMProvider) -> list[UIElement]:
    """LLM이 의미(역할·이름)만 부여 — bbox는 CV·OCR 소유 (공간 추론을 LLM에 맡기지 않음)."""
    brief = [{"id": e.id, "kind": e.kind, "label": e.label, "bbox": e.bbox}
             for e in elements]
    raw = provider.run(_LABEL_PROMPT.format(elements=json.dumps(brief, ensure_ascii=False)),
                       images=[annotated_path])
    m = _JSON_BLOCK.search(raw)
    if not m:
        return elements
    try:
        roles = {int(x["id"]): x for x in json.loads(m.group()).get("elements", [])}
    except (json.JSONDecodeError, KeyError, ValueError):
        return elements
    for e in elements:
        if e.id in roles:
            r = roles[e.id]
            e.kind = r.get("role", e.kind) or e.kind
            e.label = r.get("name") or e.label
    return elements


def save_inspection(out_dir: str | Path, png: bytes,
                    elements: list[UIElement]) -> Path:
    """카탈로그 저장: source.png / annotated.png / elements.json / crops/elem_NNN.png.

    crops는 OpenCV 템플릿 매칭용 에셋으로 바로 사용 가능 — 스크립트 작성 보조의 핵심 산출물.
    """
    out = Path(out_dir)
    (out / "crops").mkdir(parents=True, exist_ok=True)
    (out / "source.png").write_bytes(png)
    (out / "annotated.png").write_bytes(render_overlay(png, elements))
    img = _decode(png)
    for e in elements:
        l, t, r, b = e.bbox
        ok, buf = cv2.imencode(".png", img[t:b, l:r])
        if ok:
            (out / "crops" / f"elem_{e.id:03d}.png").write_bytes(buf.tobytes())
    (out / "elements.json").write_text(
        json.dumps({"elements": [asdict(e) for e in elements]}, ensure_ascii=False,
                   indent=2), encoding="utf-8")
    return out
