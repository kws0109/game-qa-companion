from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="companion",
                                description="Game QA session analyzer")
    sub = p.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="화면 캡처로 세션 기록 (관찰 전용)")
    cap.add_argument("--source", choices=["windows", "adb"], required=True)
    cap.add_argument("--game", required=True, help="게임 config yaml 경로")
    cap.add_argument("--out", default="sessions")
    cap.add_argument("--interval", type=float, default=2.0)
    cap.add_argument("--duration", type=float, default=1800.0)
    cap.add_argument("--window", default=None,
                     help="windows: 창 제목 override (기본은 config의 capture.window_title)")
    cap.add_argument("--serial", default=None,
                     help="adb: 기기 시리얼 override (기본은 config의 capture.adb_serial)")

    imp = sub.add_parser("import-artifacts", help="기존 자동화 산출물을 세션으로 변환")
    imp.add_argument("--src", required=True)
    imp.add_argument("--game-name", required=True)
    imp.add_argument("--out", default="sessions")

    an = sub.add_parser("analyze", help="세션 분석 + 리포트 생성")
    an.add_argument("--session", required=True)
    an.add_argument("--game", required=True)
    an.add_argument("--provider", choices=["claude", "fake"], default="claude")
    an.add_argument("--ocr", action="store_true", help="OCR 수치 시계열 신호 활성화")
    an.add_argument("--max-candidates", type=int, default=10,
                    help="LLM 판정 후보 수 상한 (비용 통제, 긴 신호 우선)")

    ask_p = sub.add_parser("ask", help="세션 분석 결과에 자연어 질의")
    ask_p.add_argument("--session", required=True)
    ask_p.add_argument("question")

    ins = sub.add_parser("inspect",
                         help="화면의 UI 요소 카탈로그 생성 (좌표·하이라이트·크롭 — 스크립트 작성 보조)")
    src = ins.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="분석할 스크린샷 파일")
    src.add_argument("--source", choices=["windows", "adb"], help="라이브 캡처로 1장")
    ins.add_argument("--game", default=None, help="게임 config (라이브 캡처 시 창·기기 정보)")
    ins.add_argument("--window", default=None)
    ins.add_argument("--serial", default=None)
    ins.add_argument("--provider", choices=["none", "claude", "fake"], default="none",
                     help="none=CV·OCR만(무료) / claude=역할·이름 라벨링 추가")
    ins.add_argument("--ocr", action="store_true", help="OCR 텍스트 요소 포함")
    ins.add_argument("--out", default="inspections")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "capture":
        from companion.config import GameConfig
        from companion.session import record_session
        cfg = GameConfig.load(args.game)
        if args.source == "windows":
            from companion.capture.windows import WindowsCapture
            grabber = WindowsCapture(window_title=args.window or cfg.capture_window_title)
        else:
            from companion.capture.adb import AdbCapture
            grabber = AdbCapture(serial=args.serial or cfg.capture_adb_serial)
        out = record_session(grabber, args.out, game=cfg.name, source=args.source,
                             interval=args.interval, duration=args.duration)
        print(f"session saved: {out}")
    elif args.command == "import-artifacts":
        from companion.capture.artifacts import import_artifacts
        print(f"session saved: {import_artifacts(args.src, args.out, game=args.game_name)}")
    elif args.command == "analyze":
        from companion.analysis.pipeline import analyze_session
        from companion.analysis.report import render_report
        from companion.config import GameConfig
        cfg = GameConfig.load(args.game)
        if args.provider == "claude":
            from companion.providers.claude_agent import ClaudeAgentProvider
            provider = ClaudeAgentProvider()
        else:
            from companion.providers.base import FakeProvider
            provider = FakeProvider(responses=[
                '{"verdict":"likely_normal","severity":"low","explanation":"fake"}'])
        engine = None
        if args.ocr:
            from companion.vision.ocr import OcrEngine
            engine = OcrEngine()
        result = analyze_session(args.session, cfg, provider, ocr_engine=engine,
                                 max_candidates=args.max_candidates)
        report = render_report(args.session)
        print(f"candidates: {len(result['candidates'])} / report: {report}")
    elif args.command == "ask":
        from companion.analysis.qa import ask
        from companion.providers.claude_agent import ClaudeAgentProvider
        print(ask(args.session, args.question, ClaudeAgentProvider()))
    elif args.command == "inspect":
        from datetime import datetime
        from pathlib import Path
        from companion.vision.elements import detect_elements, label_elements, save_inspection
        if args.image:
            png = Path(args.image).read_bytes()
        else:
            cfg = None
            if args.game:
                from companion.config import GameConfig
                cfg = GameConfig.load(args.game)
            if args.source == "windows":
                from companion.capture.windows import WindowsCapture
                title = args.window or (cfg.capture_window_title if cfg else None)
                png = WindowsCapture(window_title=title).grab()
            else:
                from companion.capture.adb import AdbCapture
                serial = args.serial or (cfg.capture_adb_serial if cfg else None)
                png = AdbCapture(serial=serial).grab()
        engine = None
        if args.ocr:
            from companion.vision.ocr import OcrEngine
            engine = OcrEngine()
        elements = detect_elements(png, ocr_engine=engine)
        out = save_inspection(
            Path(args.out) / datetime.now().strftime("%Y%m%d_%H%M%S"), png, elements)
        if args.provider in ("claude", "fake") and elements:
            if args.provider == "claude":
                from companion.providers.claude_agent import ClaudeAgentProvider
                provider = ClaudeAgentProvider()
            else:
                from companion.providers.base import FakeProvider
                provider = FakeProvider(responses=['{"elements":[]}'])
            elements = label_elements(elements, out / "annotated.png", provider)
            save_inspection(out, png, elements)  # 라벨 반영해 갱신
        print(f"elements: {len(elements)} / catalog: {out}")


if __name__ == "__main__":
    main()
