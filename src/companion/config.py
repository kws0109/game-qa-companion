from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

Region = tuple[int, int, int, int]  # (left, top, right, bottom)


@dataclass
class Template:
    id: str
    image: str
    region: Region | None = None


@dataclass
class OcrRegion:
    id: str
    region: Region
    numeric: bool = False


@dataclass
class GameConfig:
    name: str
    type: str
    templates: list[Template] = field(default_factory=list)
    ocr_regions: list[OcrRegion] = field(default_factory=list)
    analysis_prompts: dict[str, str] = field(default_factory=dict)
    # capture 섹션 — 게임별 캡처 대상의 동적 할당 (CLI 플래그는 override 용도로만)
    capture_window_title: str | None = None  # 창 제목 부분 일치 (suffix 변동 흡수)
    capture_adb_serial: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> "GameConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for key in ("name", "type"):
            if not data.get(key):
                raise ValueError(f"config missing required key: {key}")
        templates = [
            Template(id=t["id"], image=t["image"],
                     region=tuple(t["region"]) if t.get("region") else None)
            for t in data.get("templates", [])
        ]
        ocr_regions = [
            OcrRegion(id=o["id"], region=tuple(o["region"]),
                      numeric=bool(o.get("numeric", False)))
            for o in data.get("ocr_regions", [])
        ]
        capture = data.get("capture") or {}
        return cls(name=data["name"], type=data["type"], templates=templates,
                   ocr_regions=ocr_regions,
                   analysis_prompts=dict(data.get("analysis_prompts", {})),
                   capture_window_title=capture.get("window_title"),
                   capture_adb_serial=capture.get("adb_serial"))
