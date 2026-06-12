from __future__ import annotations

import json
from pathlib import Path


def list_game_configs(root: str | Path) -> list[Path]:
    d = Path(root) / "configs"
    return sorted(d.glob("*.yaml")) if d.exists() else []


def list_sessions(root: str | Path) -> list[dict]:
    """sessions/ 하위 세션 요약 — GUI 테이블용. 최신순."""
    base = Path(root) / "sessions"
    out: list[dict] = []
    if not base.exists():
        return out
    for d in sorted([p for p in base.iterdir() if p.is_dir()], reverse=True):
        manifest = d / "manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        frames = data.get("frames", [])
        size_mb = sum(f.stat().st_size for f in (d / "frames").glob("*.png")) / 1e6 \
            if (d / "frames").exists() else 0.0
        out.append({
            "name": d.name, "path": d, "game": data.get("game", "?"),
            "frames": len(frames), "size_mb": round(size_mb, 1),
            "analyzed": (d / "analysis.json").exists(),
            "last_frame": (d / frames[-1]["file"]) if frames else None,
        })
    return out


def make_provider(name: str):
    """GUI provider 선택 — fake(무료 드라이런) / claude(구독 연동)."""
    if name == "claude":
        from companion.providers.claude_agent import ClaudeAgentProvider
        return ClaudeAgentProvider()
    from companion.providers.base import FakeProvider
    return FakeProvider(responses=[
        '{"verdict":"likely_normal","severity":"low","explanation":"fake provider 드라이런"}'])
