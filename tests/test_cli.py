from companion.cli import build_parser


def test_parser_capture_windows():
    args = build_parser().parse_args(
        ["capture", "--source", "windows", "--game", "configs/example.yaml",
         "--interval", "2", "--duration", "1800"])
    assert args.command == "capture" and args.source == "windows"
    assert args.window is None and args.duration == 1800.0  # 창 제목은 config에서


def test_parser_capture_window_override():
    args = build_parser().parse_args(
        ["capture", "--source", "windows", "--game", "configs/example.yaml",
         "--window", "OTHER TITLE"])
    assert args.window == "OTHER TITLE"  # CLI는 config override 용도


def test_parser_analyze_defaults_to_claude():
    args = build_parser().parse_args(
        ["analyze", "--session", "sessions/x", "--game", "configs/example.yaml"])
    assert args.command == "analyze" and args.provider == "claude"


def test_parser_ask():
    args = build_parser().parse_args(["ask", "--session", "sessions/x", "왜 멈췄어?"])
    assert args.question == "왜 멈췄어?"
