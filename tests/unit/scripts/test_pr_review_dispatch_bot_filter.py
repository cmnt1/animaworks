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


def test_check_comments_dispatches_bot_mention_directly(mod, monkeypatch):
    comment = {
        "id": 9,
        "user": {"login": "external"},
        "body": "@DEV-BOT fix this",
        "html_url": "https://gh.test/o/r/pull/17#issuecomment-9",
        "issue_url": "https://api.github.test/repos/o/r/issues/17",
    }
    monkeypatch.setattr(
        mod,
        "gh",
        lambda args: json.dumps([comment]) if "/issues/comments" in args[1] else "[]",
    )
    send = MagicMock()
    task = MagicMock(return_value=True)
    monkeypatch.setattr(mod, "send", send)
    monkeypatch.setattr(mod, "dispatch_task", task)
    state = {"last_comment_check": "2026-07-14T00:00:00Z", "seen_comments": {}}

    mod.check_comments(state)

    send.assert_not_called()
    assert task.call_args.kwargs["task_id"] == "gh-cmd-9"
    assert task.call_args.kwargs["target"] == "natsume"
    assert "o/r#17" in task.call_args.kwargs["instruction"]


def test_check_ci_dispatches_failure_directly(mod, monkeypatch):
    monkeypatch.setattr(
        mod,
        "gh",
        lambda args: json.dumps(
            [
                {
                    "number": 17,
                    "headRefOid": "a" * 40,
                    "statusCheckRollup": [
                        {
                            "name": "tests",
                            "conclusion": "FAILURE",
                            "detailsUrl": "https://gh.test/actions/1",
                        }
                    ],
                }
            ]
        ),
    )
    task = MagicMock(return_value=True)
    monkeypatch.setattr(mod, "dispatch_task", task)
    state = mod.default_state()

    mod.check_ci(state)

    kwargs = task.call_args.kwargs
    assert kwargs["target"] == "natsume"
    assert kwargs["task_id"] == "gh-ci-o-r#17-aaaaaaaa"
    assert "CI (tests)" in kwargs["instruction"]
    assert "https://gh.test/actions/1" in kwargs["instruction"]
    assert "o/r#17_aaaaaaaa" in state["ci_notified"]


def test_check_ci_new_failure_type_on_same_sha_dispatches_again(mod, monkeypatch):
    monkeypatch.setattr(
        mod,
        "gh",
        lambda args: json.dumps(
            [
                {
                    "number": 17,
                    "headRefOid": "a" * 40,
                    "statusCheckRollup": [{"name": "new-check", "conclusion": "FAILURE"}],
                }
            ]
        ),
    )
    task = MagicMock(return_value=True)
    monkeypatch.setattr(mod, "dispatch_task", task)
    state = mod.default_state()
    key = "o/r#17_aaaaaaaa"
    state["ci_notified"][key] = "2026-08-11T00:00:00Z"
    state["ci_failure_signatures"][key] = "old-check"

    mod.check_ci(state)

    task.assert_called_once()
    assert state["ci_failure_signatures"][key] == "new-check"


def test_dispatch_task_dry_run_only_logs(mod, monkeypatch):
    direct = MagicMock()
    monkeypatch.setattr(mod, "DRY_RUN", True)
    monkeypatch.setattr(mod, "dispatch_direct_task", direct)

    assert (
        mod.dispatch_task(
            target="natsume",
            task_id="gh-cmd-1",
            summary="dry run",
            instruction="noop",
        )
        is False
    )
    direct.assert_not_called()
    assert "DRY_RUN task -> natsume: gh-cmd-1 dry run" in mod.LOG_FILE.read_text(encoding="utf-8")


def test_changes_requested_dispatches_review_task_once(mod, monkeypatch):
    task = MagicMock(return_value=True)
    monkeypatch.setattr(mod, "dispatch_task", task)
    state = mod.default_state()
    item = {
        "review_id": 77,
        "repo": "o/r",
        "number": 17,
        "author": "review-bot",
        "body": "x" * 600,
        "url": "https://gh.test/o/r/pull/17#review-77",
        "bot_derived": True,
    }

    mod._dispatch_review_task_once(state, item)
    mod._dispatch_review_task_once(state, item)

    task.assert_called_once()
    kwargs = task.call_args.kwargs
    assert kwargs["task_id"] == "gh-review-o-r#17-77"
    assert "bot由来" in kwargs["instruction"]
    assert "x" * 500 in kwargs["instruction"]
    assert "x" * 501 not in kwargs["instruction"]
    assert "独断で押し切らず上長(rin)へ報告" in kwargs["instruction"]
    assert list(state["review_tasks"]) == ["77"]
