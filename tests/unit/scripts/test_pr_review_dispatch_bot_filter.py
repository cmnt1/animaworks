"""is_our_bot / reviewer exclusion unit tests for pr-review-dispatch.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "pr-review-dispatch.py"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_SHARED_DIR", str(tmp_path))
    monkeypatch.setenv("PR_DISPATCH_REPOS", "o/r")
    monkeypatch.setenv("PR_DISPATCH_BOT_LOGIN", "dev-bot")
    monkeypatch.setenv("PR_DISPATCH_REVIEWER_LOGIN", "review-bot")
    spec = importlib.util.spec_from_file_location("pr_review_dispatch_bot_filter", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.REPOS = ["o/r"]
    module.BOT_LOGIN = "dev-bot"
    module.REVIEWER_LOGIN = "review-bot"
    return module


def test_is_our_bot_matches_bot_and_reviewer(mod):
    assert mod.is_our_bot("dev-bot") is True
    assert mod.is_our_bot("review-bot") is True
    assert mod.is_our_bot("human") is False
    assert mod.is_our_bot("") is False


def test_is_our_bot_empty_logins_match_nobody(mod):
    mod.BOT_LOGIN = ""
    mod.REVIEWER_LOGIN = ""
    assert mod.is_our_bot("dev-bot") is False
    assert mod.is_our_bot("review-bot") is False


def test_check_comments_excludes_reviewer_login(mod, monkeypatch):
    def fake_gh(args: list[str]) -> str:
        endpoint = args[1] if len(args) > 1 else ""
        if "/pulls/comments" in endpoint:
            return json.dumps(
                [
                    {
                        "id": 1,
                        "user": {"login": "review-bot"},
                        "body": "internal review note",
                        "html_url": "https://gh.test/1",
                    },
                    {
                        "id": 2,
                        "user": {"login": "dev-bot"},
                        "body": "bot push note",
                        "html_url": "https://gh.test/2",
                    },
                    {
                        "id": 3,
                        "user": {"login": "external"},
                        "body": "please fix",
                        "html_url": "https://gh.test/3",
                    },
                ]
            )
        return json.dumps([])

    send = MagicMock()
    monkeypatch.setattr(mod, "gh", fake_gh)
    monkeypatch.setattr(mod, "send", send)

    state: dict = {
        "last_comment_check": "2026-07-14T00:00:00Z",
        "seen_comments": {},
    }
    mod.check_comments(state)

    send.assert_called_once()
    content = send.call_args[0][1]
    assert "external" in content
    assert "please fix" in content
    assert "review-bot" not in content
    assert "dev-bot" not in content
    assert "review-comment:3" in state["seen_comments"]
    assert "review-comment:1" not in state["seen_comments"]
    assert "review-comment:2" not in state["seen_comments"]
