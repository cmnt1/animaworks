# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for external task source collectors (mocked I/O only)."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import ToolConfigError
from core.external_tasks.collector import CredentialNotFoundError
from core.external_tasks.sources import chatwork as chatwork_src
from core.external_tasks.sources import github as github_src
from core.external_tasks.sources import gmail as gmail_src
from core.external_tasks.sources import slack as slack_src


# ── GitHub ──────────────────────────────────────────────


def _gh_auth_ok(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    if cmd[:3] == ["gh", "auth", "status"]:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    raise AssertionError(f"unexpected gh command: {cmd}")


def test_github_collects_prs_and_issues() -> None:
    pr_payload = [
        {
            "number": 10,
            "title": "Fix login",
            "url": "https://github.com/acme/app/pull/10",
            "createdAt": "2026-07-18T01:00:00Z",
            "updatedAt": "2026-07-19T02:00:00Z",
            "repository": {"name": "app", "nameWithOwner": "acme/app"},
        }
    ]
    issue_payload = [
        {
            "number": 3,
            "title": "Bug report",
            "url": "https://github.com/acme/app/issues/3",
            "createdAt": "2026-07-17T01:00:00Z",
            "updatedAt": "2026-07-18T02:00:00Z",
            "repository": {"name": "app", "nameWithOwner": "acme/app"},
        }
    ]

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[1:3] == ["search", "prs"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(pr_payload), "")
        if cmd[1:3] == ["search", "issues"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(issue_payload), "")
        raise AssertionError(f"unexpected gh command: {cmd}")

    with patch("core.external_tasks.sources.github.subprocess.run", side_effect=fake_run):
        tasks = github_src.collect_github()

    assert len(tasks) == 2
    pr = next(t for t in tasks if t.id.startswith("github-pr-"))
    issue = next(t for t in tasks if t.id.startswith("github-issue-"))

    assert pr.id == "github-pr-acme-app-10"
    assert pr.priority == 90
    assert pr.title == "app #10: Fix login"
    assert pr.source_type == "github"
    assert pr.source_icon == "github"
    assert pr.source_url == "https://github.com/acme/app/pull/10"
    assert pr.created_at == "2026-07-18T01:00:00Z"
    assert pr.last_updated_at == "2026-07-19T02:00:00Z"
    assert pr.status == "open"

    assert issue.id == "github-issue-acme-app-3"
    assert issue.priority == 75
    assert issue.title == "app #3: Bug report"


def test_github_credential_missing_when_gh_not_installed() -> None:
    with patch(
        "core.external_tasks.sources.github.subprocess.run",
        side_effect=FileNotFoundError("gh"),
    ):
        with pytest.raises(CredentialNotFoundError):
            github_src.collect_github()


def test_github_credential_missing_when_unauthenticated() -> None:
    with patch(
        "core.external_tasks.sources.github.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["gh", "auth", "status"]),
    ):
        with pytest.raises(CredentialNotFoundError):
            github_src.collect_github()


def test_github_api_error_propagates() -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 1, "", "API rate limit exceeded")

    with patch("core.external_tasks.sources.github.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="gh command failed"):
            github_src.collect_github()


def test_github_id_deterministic() -> None:
    payload = [
        {
            "number": 42,
            "title": "X",
            "url": "https://github.com/o/r/pull/42",
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-02T00:00:00Z",
            "repository": {"name": "r", "nameWithOwner": "o/r"},
        }
    ]

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[1:3] == ["search", "prs"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")
        if cmd[1:3] == ["search", "issues"]:
            return subprocess.CompletedProcess(cmd, 0, "[]", "")
        raise AssertionError(cmd)

    with patch("core.external_tasks.sources.github.subprocess.run", side_effect=fake_run):
        a = github_src.collect_github()
        b = github_src.collect_github()
    assert a[0].id == b[0].id == "github-pr-o-r-42"


# ── Slack ───────────────────────────────────────────────


def test_slack_collects_unreplied_mentions() -> None:
    mock_client = MagicMock()
    mock_client.my_user_id = "Ume"
    mock_client.auth_test.return_value = {"user_id": "Ume"}
    mock_client.get_channel_name.return_value = "ops"
    mock_client._call.return_value = {
        "permalink": "https://app.slack.com/archives/C1/p1234567890000000"
    }

    # Use a near-current epoch so the 7-day filter accepts it.
    import time

    ts = f"{time.time() - 3600:.6f}"
    mention = {
        "channel_id": "C1",
        "ts": ts,
        "ts_epoch": float(ts),
        "user_id": "Uother",
        "text": "please check this deploy",
        "channel_name": "ops",
        "thread_ts": "",
    }

    mock_cache = MagicMock()
    mock_cache.find_unreplied.return_value = [mention]

    with (
        patch("core.tools._slack_client.SlackClient", return_value=mock_client),
        patch("core.tools._slack_cache.MessageCache", return_value=mock_cache),
    ):
        tasks = slack_src.collect_slack()

    assert len(tasks) == 1
    t = tasks[0]
    assert t.id == f"slack-C1-{ts}"
    assert t.priority == 80
    assert t.title == "#ops: please check this deploy"
    assert t.source_type == "slack"
    assert t.source_url == "https://app.slack.com/archives/C1/p1234567890000000"
    mock_cache.close.assert_called_once()


def test_slack_credential_missing() -> None:
    with patch(
        "core.tools._slack_client.SlackClient",
        side_effect=ToolConfigError("missing slack token"),
    ):
        with pytest.raises(CredentialNotFoundError, match="missing slack token"):
            slack_src.collect_slack()


def test_slack_api_error_propagates() -> None:
    mock_client = MagicMock()
    mock_client.auth_test.side_effect = RuntimeError("slack down")

    with (
        patch("core.tools._slack_client.SlackClient", return_value=mock_client),
        patch("core.tools._slack_cache.MessageCache"),
    ):
        with pytest.raises(RuntimeError, match="slack down"):
            slack_src.collect_slack()


def test_slack_is_actionable_mention_filters_old_and_self() -> None:
    import time

    now = time.time()
    cutoff = now - 7 * 86400
    old = {"user_id": "U2", "ts_epoch": now - 10 * 86400, "ts": str(now - 10 * 86400)}
    own = {"user_id": "Ume", "ts_epoch": now - 100, "ts": str(now - 100)}
    ok = {"user_id": "U2", "ts_epoch": now - 100, "ts": str(now - 100)}
    assert slack_src.is_actionable_mention(old, "Ume", cutoff_epoch=cutoff) is False
    assert slack_src.is_actionable_mention(own, "Ume", cutoff_epoch=cutoff) is False
    assert slack_src.is_actionable_mention(ok, "Ume", cutoff_epoch=cutoff) is True


# ── Chatwork ────────────────────────────────────────────


def test_chatwork_collects_open_tasks() -> None:
    mock_client = MagicMock()
    mock_client.my_tasks.return_value = [
        {
            "task_id": 99,
            "body": "[info]Please review the contract[/info]",
            "message_id": "m55",
            "limit_time": 1720000000,
            "room": {"room_id": 12345, "name": "Legal"},
        }
    ]
    mock_client.me.return_value = {"account_id": 7}

    mock_cache = MagicMock()
    mock_cache.find_unreplied.return_value = []

    with (
        patch("core.tools._chatwork_client.ChatworkClient", return_value=mock_client),
        patch("core.tools._chatwork_cache.MessageCache", return_value=mock_cache),
    ):
        tasks = chatwork_src.collect_chatwork()

    assert len(tasks) == 1
    t = tasks[0]
    assert t.id == "chatwork-task-99"
    assert t.priority == 85
    assert t.title.startswith("Legal:")
    assert "Please review the contract" in t.title
    assert t.source_url == "https://www.chatwork.com/#!rid12345-m55"
    assert t.source_type == "chatwork"
    assert t.source_icon == "chatwork"


def test_chatwork_collects_unreplied_mentions() -> None:
    import time

    send_time = int(time.time()) - 100
    mock_client = MagicMock()
    mock_client.my_tasks.return_value = []
    mock_client.me.return_value = {"account_id": 7}

    mock_cache = MagicMock()
    mock_cache.find_unreplied.return_value = [
        {
            "room_id": "100",
            "message_id": "200",
            "room_name": "Ops",
            "body": "[To:7] Alice\nNeed your OK",
            "send_time": send_time,
        }
    ]

    with (
        patch("core.tools._chatwork_client.ChatworkClient", return_value=mock_client),
        patch("core.tools._chatwork_cache.MessageCache", return_value=mock_cache),
    ):
        tasks = chatwork_src.collect_chatwork()

    assert len(tasks) == 1
    t = tasks[0]
    assert t.id == "chatwork-msg-100-200"
    assert t.priority == 80
    assert t.title == "Ops: Need your OK"
    assert t.source_url == "https://www.chatwork.com/#!rid100-200"


def test_chatwork_credential_missing() -> None:
    with patch(
        "core.tools._chatwork_client.ChatworkClient",
        side_effect=ToolConfigError("missing chatwork token"),
    ):
        with pytest.raises(CredentialNotFoundError, match="missing chatwork token"):
            chatwork_src.collect_chatwork()


def test_chatwork_api_error_propagates() -> None:
    mock_client = MagicMock()
    mock_client.my_tasks.side_effect = RuntimeError("chatwork 500")

    with patch("core.tools._chatwork_client.ChatworkClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="chatwork 500"):
            chatwork_src.collect_chatwork()


# ── Gmail ───────────────────────────────────────────────


def test_gmail_collects_unread() -> None:
    email = SimpleNamespace(
        id="msgABC",
        thread_id="thr1",
        from_addr="Alice <alice@example.com>",
        subject="Estimate review",
        snippet="...",
        date="Sat, 19 Jul 2026 10:00:00 +0000",
    )
    mock_client = MagicMock()
    mock_client.search_emails.return_value = [email]

    with patch("core.tools.gmail.GmailClient", return_value=mock_client):
        tasks = gmail_src.collect_gmail()

    assert len(tasks) == 1
    t = tasks[0]
    assert t.id == "gmail-msgABC"
    assert t.priority == 70
    assert t.title == "Alice: Estimate review"
    assert t.source_url == "https://mail.google.com/mail/u/0/#inbox/msgABC"
    assert t.source_type == "gmail"
    assert t.source_icon == "gmail"
    mock_client.search_emails.assert_called_once_with(
        "is:unread in:inbox newer_than:7d",
        max_results=20,
    )


def test_gmail_credential_missing_on_import_error() -> None:
    with patch(
        "core.tools.gmail.GmailClient",
        side_effect=ImportError("google-api packages missing"),
    ):
        with pytest.raises(CredentialNotFoundError, match="google-api"):
            gmail_src.collect_gmail()


def test_gmail_credential_missing_on_value_error() -> None:
    mock_client = MagicMock()
    mock_client.search_emails.side_effect = ValueError("No OAuth credentials found")

    with patch("core.tools.gmail.GmailClient", return_value=mock_client):
        with pytest.raises(CredentialNotFoundError, match="OAuth"):
            gmail_src.collect_gmail()


def test_gmail_api_error_propagates() -> None:
    mock_client = MagicMock()
    mock_client.search_emails.side_effect = RuntimeError("quota exceeded")

    with patch("core.tools.gmail.GmailClient", return_value=mock_client):
        with pytest.raises(RuntimeError, match="quota exceeded"):
            gmail_src.collect_gmail()


def test_gmail_id_deterministic() -> None:
    email = SimpleNamespace(
        id="stable-id",
        thread_id="t",
        from_addr="bob@example.com",
        subject="Hi",
        snippet="",
        date="",
    )
    mock_client = MagicMock()
    mock_client.search_emails.return_value = [email]

    with patch("core.tools.gmail.GmailClient", return_value=mock_client):
        a = gmail_src.collect_gmail()
        b = gmail_src.collect_gmail()
    assert a[0].id == b[0].id == "gmail-stable-id"
