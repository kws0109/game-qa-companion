import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from companion.gui.claude_status import claude_status


def test_status_reads_oauth_account(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".claude.json").write_text(json.dumps(
        {"oauthAccount": {"emailAddress": "kws@example.com",
                          "organizationName": "Personal"}}), encoding="utf-8")
    s = claude_status(home=tmp_path)
    assert s["email"] == "kws@example.com" and s["org"] == "Personal"
    assert s["api_key_present"] is False


def test_status_without_login(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = claude_status(home=tmp_path)
    assert s["email"] is None


def test_status_flags_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert claude_status(home=tmp_path)["api_key_present"] is True
