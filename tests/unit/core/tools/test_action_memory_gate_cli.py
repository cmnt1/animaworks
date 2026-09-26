from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class FakeRule:
    doc_id: str
    content: str
    score: float = 0.95


def _install_fake_gmail(monkeypatch: pytest.MonkeyPatch) -> list:
    """Install a fake core.tools.gmail module so cli_dispatch can run it inline."""
    called: list = []
    fake_mod = types.ModuleType("core.tools.gmail")

    def fake_cli_main(_argv):
        called.append(_argv)

    fake_mod.cli_main = fake_cli_main
    monkeypatch.setitem(sys.modules, "core.tools.gmail", fake_mod)
    return called


def test_cli_prints_action_rules_to_stderr_and_executes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from core.memory import action_gate
    from core.tools import cli_dispatch

    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "knowledge").mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
    monkeypatch.setattr(sys, "argv", ["animaworks-tool", "gmail", "draft", "--to", "a@example.com"])

    called = _install_fake_gmail(monkeypatch)

    rule = FakeRule(
        "rule-cli",
        "## [ACTION-RULE] CLI check\ntrigger_tools: gmail_draft\n---\n本文のルール",
    )
    monkeypatch.setattr(action_gate, "_search_action_rules", lambda *args, **kwargs: [rule])

    cli_dispatch()  # should NOT sys.exit(1)

    stderr = capsys.readouterr().err
    assert '<action-rule path="rule-cli"' in stderr
    assert "本文のルール" in stderr
    assert called == [["draft", "--to", "a@example.com"]]


def test_cli_without_rules_still_executes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from core.memory import action_gate
    from core.tools import cli_dispatch

    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "knowledge").mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
    monkeypatch.setattr(sys, "argv", ["animaworks-tool", "gmail", "draft", "--to", "a@example.com"])

    called = _install_fake_gmail(monkeypatch)
    monkeypatch.setattr(action_gate, "_search_action_rules", lambda *args, **kwargs: [])

    cli_dispatch()

    assert capsys.readouterr().err == ""
    assert called == [["draft", "--to", "a@example.com"]]
