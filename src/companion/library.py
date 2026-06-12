from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def _slug(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "_", text).strip("_").lower()
    return s or "elem"


class ElementLibrary:
    """게임별 확정 UI 요소 저장소 (트리: 게임 → 화면 → 요소).

    QA가 검수해 등록한 요소는 이후 인식·LLM 판단의 기준(정답)이 된다 —
    apply_library가 화면에서 다시 찾아 라벨을 강제하고, LLM은 이를 덮어쓸 수 없다.
    저장: library/<게임slug>/elements.json + templates/<요소id>.png
    """

    def __init__(self, root: str | Path, game: str):
        self.game = game
        self.dir = Path(root) / "library" / _slug(game)
        self.file = self.dir / "elements.json"
        self.data: dict = {"game": game, "screens": {}}
        if self.file.exists():
            self.data = json.loads(self.file.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    def tree(self) -> dict:
        return self.data["screens"]

    def all_elements(self) -> list[tuple[str, str, dict]]:
        out = []
        for screen, body in self.data["screens"].items():
            for eid, rec in body["elements"].items():
                out.append((screen, eid, rec))
        return out

    def add(self, screen: str, name: str, kind: str,
            bbox: tuple[int, int, int, int], center: tuple[int, int],
            crop_png: bytes | None,
            resolution: tuple[int, int] | None = None) -> str:
        elements = self.data["screens"].setdefault(screen, {"elements": {}})["elements"]
        eid = base = _slug(name)
        n = 2
        while eid in elements:
            eid = f"{base}_{n}"
            n += 1
        template = None
        if crop_png:
            (self.dir / "templates").mkdir(parents=True, exist_ok=True)
            template = f"templates/{eid}.png"
            (self.dir / template).write_bytes(crop_png)
        elements[eid] = {
            "name": name, "kind": kind, "bbox": list(bbox), "center": list(center),
            "template": template,
            "resolution": list(resolution) if resolution else None,  # 좌표·템플릿의 기준 해상도
            "confirmed_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.save()
        return eid

    def remove(self, screen: str, eid: str) -> None:
        body = self.data["screens"].get(screen)
        if not body or eid not in body["elements"]:
            return
        rec = body["elements"].pop(eid)
        if rec.get("template"):
            (self.dir / rec["template"]).unlink(missing_ok=True)
        if not body["elements"]:
            del self.data["screens"][screen]
        self.save()

    def template_bytes(self, rec: dict) -> bytes | None:
        if not rec.get("template"):
            return None
        p = self.dir / rec["template"]
        return p.read_bytes() if p.exists() else None
