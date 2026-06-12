from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from companion.providers.base import LLMProvider
from companion.vision.analyzer import match_template

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class UIElement:
    id: int
    kind: str  # CV 단계: "box" | "text" — LLM 라벨링 후: button/icon/gauge/panel 등
    label: str
    bbox: tuple[int, int, int, int]  # (l, t, r, b)
    center: tuple[int, int]
    confirmed: bool = False  # 라이브러리 확정 요소 — LLM이 덮어쓸 수 없음


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


def stability_mask_from_pngs(pngs: list[bytes], *,
                             std_threshold: float = 30.0) -> np.ndarray:
    """프레임 묶음의 픽셀 표준편차로 '시간축 안정 영역' 마스크 생성.

    UI(HUD·버튼·패널)는 프레임이 지나도 같은 자리 — 분산이 낮다.
    3D 월드(지형·캐릭터·카메라·파티클)는 계속 변한다 — 분산이 높다.
    반환: 안정 영역=255, 가변 영역=0 (uint8).
    """
    grays = []
    shape = None
    for b in pngs:
        g = cv2.cvtColor(_decode(b), cv2.COLOR_BGR2GRAY)
        if shape is None:
            shape = g.shape
        elif g.shape != shape:
            g = cv2.resize(g, (shape[1], shape[0]))
        grays.append(g.astype(np.float32))
    std = np.std(np.stack(grays), axis=0)
    mask = (std < std_threshold).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


def stability_mask(session_dir: str | Path, *, sample: int = 20,
                   std_threshold: float = 30.0) -> np.ndarray:
    """세션 프레임을 샘플링해 안정성 마스크 생성 (stability_mask_from_pngs 위임)."""
    from companion.session import Manifest
    d = Path(session_dir)
    m = Manifest.load(d)
    step = max(1, len(m.frames) // sample)
    pngs = [(d / fr.file).read_bytes() for fr in m.frames[::step][:sample]]
    return stability_mask_from_pngs(pngs, std_threshold=std_threshold)


def _straightness(edge_roi: np.ndarray) -> float:
    """축 정렬 직선성 — UI 박스 판별 신호.

    UI 요소의 테두리는 수평·수직 직선이라, 어떤 행/열은 엣지 픽셀로 거의 가득 찬다.
    바위·초목 같은 유기적 형태의 바운딩 박스는 그런 행과 열을 동시에 갖지 못한다.
    반환: min(최대 행 채움률, 최대 열 채움률) — 0(유기적)~1(완전한 사각 테두리).
    """
    h, w = edge_roi.shape[:2]
    if h < 2 or w < 2:
        return 0.0
    on = (edge_roi > 0).astype(np.float32)
    row_frac = float(on.sum(axis=1).max()) / w
    col_frac = float(on.sum(axis=0).max()) / h
    return min(row_frac, col_frac)


def detect_boxes(png: bytes, *, min_side: int = 24, max_area_ratio: float = 0.3,
                 mask: np.ndarray | None = None, mask_coverage: float = 0.6,
                 min_straightness: float = 0.0) -> list[tuple[int, int, int, int]]:
    """엣지 기반 사각 UI 요소 후보 검출.

    필터: mask(시간축 안정 영역과 60% 이상 겹침). min_straightness는 실험용 —
    나이트 크로우 실측에서 반투명 UI를 죽이고 텍스처를 못 걸러 기본 비활성(0).
    """
    img = _decode(png)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges_raw = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges_raw, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cand = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < min_side or bh < min_side:
            continue
        if bw * bh > max_area_ratio * w * h:
            continue
        if mask is not None:
            mh, mw = mask.shape[:2]
            if (mh, mw) != (h, w):
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            region = mask[y:y + bh, x:x + bw]
            if float(np.mean(region > 0)) < mask_coverage:
                continue  # 월드(가변 영역) 위의 박스 — 버림
        if min_straightness > 0 and \
                _straightness(edges_raw[y:y + bh, x:x + bw]) < min_straightness:
            continue  # 축 정렬 테두리 없음 — 유기적 형태(월드 오브젝트)로 판단
        cand.append((x, y, x + bw, y + bh))
    kept: list[tuple] = []
    for b in sorted(cand, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        if all(_iou(b, k) < 0.6 for k in kept):
            kept.append(b)
    kept.sort(key=lambda b: (b[1], b[0]))  # 좌상단 순 — id 안정성
    return kept


def detect_elements(png: bytes, ocr_engine=None,
                    mask: np.ndarray | None = None,
                    text_anchor: bool = False) -> list[UIElement]:
    """CV 박스 + (선택) OCR 텍스트를 합쳐 요소 카탈로그 생성. 전부 로컬 — 비용 0.

    text_anchor=True (OCR 필요): 텍스트를 품지 않고 화면 가장자리도 아닌 박스를 제거 —
    "UI 요소는 거의 항상 텍스트를 동반한다"는 휴리스틱. 아이콘 전용 버튼을 위해 가장자리는 예외.
    """
    elements: list[UIElement] = []
    boxes = detect_boxes(png, mask=mask)
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
    if text_anchor and ocr_engine is not None:
        h, w = _decode(png).shape[:2]
        margin = 0.08

        def _near_edge(b: tuple) -> bool:
            return (b[0] <= w * margin or b[1] <= h * margin
                    or b[2] >= w * (1 - margin) or b[3] >= h * (1 - margin))

        elements = [e for e in elements
                    if e.kind != "box" or e.label or _near_edge(e.bbox)]
    elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))
    for i, e in enumerate(elements, 1):
        e.id = i
    return elements


def render_overlay(png: bytes, elements: list[UIElement]) -> bytes:
    """요소 bbox + id 번호를 그린 주석 이미지 — 스크립트 작성자가 보는 지도."""
    img = _decode(png)
    for e in elements:
        l, t, r, b = e.bbox
        color = (255, 160, 0) if e.confirmed else (0, 255, 0)  # 확정=파랑, 후보=초록
        cv2.rectangle(img, (l, t), (r, b), color, 2)
        tag = f"{e.id}"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img, (l, t - th - 8), (l + tw + 8, t), color, -1)
        cv2.putText(img, tag, (l + 4, t - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 0), 2)
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def apply_library(png: bytes, elements: list[UIElement], library) -> list[UIElement]:
    """확정 요소를 화면에서 템플릿 매칭으로 찾아 라벨을 강제 — AI 오판 방지 1단계.

    확정 요소가 검출 박스와 겹치면 그 박스에 정답 라벨을 부여하고,
    검출이 놓쳤으면 확정 요소를 직접 추가한다. confirmed=True는 LLM이 못 건드린다.
    """
    for _screen, _eid, rec in library.all_elements():
        tpl = library.template_bytes(rec)
        if not tpl:
            continue
        score, (x, y) = match_template(png, tpl)
        if score < 0.85:
            continue  # 이 화면에 없는 요소
        bw = rec["bbox"][2] - rec["bbox"][0]
        bh = rec["bbox"][3] - rec["bbox"][1]
        found = (x, y, x + bw, y + bh)
        target = next((e for e in elements if _iou(found, e.bbox) >= 0.4), None)
        if target is None:
            target = UIElement(0, rec["kind"], rec["name"], found,
                               (x + bw // 2, y + bh // 2))
            elements.append(target)
        target.kind = rec["kind"]
        target.label = rec["name"]
        target.confirmed = True
    elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))
    for i, e in enumerate(elements, 1):
        e.id = i
    return elements


_LABEL_PROMPT = """다음은 게임 화면에서 자동 검출된 UI 요소 목록이다. 주석 이미지의 초록 번호와 대응한다.

{elements}

confirmed: true 인 요소는 QA가 이미 확정한 정답이다 — 응답에 포함하지 말고 다른 해석을 제시하지 말 것.

주석 이미지를 Read 도구로 **한 번만** 읽고, 나머지 요소의 역할과 이름을 판단해 아래 JSON으로만 답하라:
{{"elements": [{{"id": 1, "role": "button|icon|gauge|text|panel|minimap|unknown", "name": "짧은 한국어 이름"}}]}}

규칙: 좌표·id는 절대 수정하지 말 것. 화면에서 식별 불가능한 요소는 role을 unknown으로."""


def label_elements(elements: list[UIElement], annotated_path: Path,
                   provider: LLMProvider) -> list[UIElement]:
    """LLM이 의미(역할·이름)만 부여 — bbox는 CV·OCR 소유 (공간 추론을 LLM에 맡기지 않음).

    안전장치: confirmed 요소는 프롬프트 지시와 무관하게 코드에서 LLM 응답 적용을 차단.
    """
    brief = [{"id": e.id, "kind": e.kind, "label": e.label, "bbox": e.bbox,
              "confirmed": e.confirmed} for e in elements]
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
        if e.confirmed:
            continue  # 확정 요소는 LLM 응답을 아예 적용하지 않음 (코드 레벨 가드)
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
