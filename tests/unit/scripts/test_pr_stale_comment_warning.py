"""is_addressed / determine_warning_stage のユニットテスト（pr-review-dispatch.py）。"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "pr-review-dispatch.py"

T0 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_SHARED_DIR", str(tmp_path))
    monkeypatch.setenv("PR_DISPATCH_REPOS", "o/r")
    monkeypatch.setenv("PR_DISPATCH_BOT_LOGIN", "bot-user")
    spec = importlib.util.spec_from_file_location("pr_stale_comment_warning", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.REPOS = ["o/r"]
    module.BOT_LOGIN = "bot-user"
    return module


# ---------------------------------------------------------------------------
# is_addressed
# ---------------------------------------------------------------------------


def test_is_addressed_pr_closed(mod):
    assert mod.is_addressed(
        pr_closed=True,
        thread_resolved=False,
        item_created_at=T0,
        bot_commit_at=None,
        bot_comment_at=None,
    )


def test_is_addressed_thread_resolved(mod):
    assert mod.is_addressed(
        pr_closed=False,
        thread_resolved=True,
        item_created_at=T0,
        bot_commit_at=None,
        bot_comment_at=None,
    )


def test_is_addressed_bot_commit_after(mod):
    assert mod.is_addressed(
        pr_closed=False,
        thread_resolved=False,
        item_created_at=T0,
        bot_commit_at=T0 + timedelta(hours=1),
        bot_comment_at=None,
    )


def test_is_addressed_bot_commit_before_not_addressed(mod):
    assert not mod.is_addressed(
        pr_closed=False,
        thread_resolved=False,
        item_created_at=T0,
        bot_commit_at=T0 - timedelta(minutes=1),
        bot_comment_at=None,
    )


def test_is_addressed_bot_comment_after(mod):
    assert mod.is_addressed(
        pr_closed=False,
        thread_resolved=False,
        item_created_at=T0,
        bot_commit_at=None,
        bot_comment_at=T0 + timedelta(minutes=30),
    )


def test_is_addressed_still_open(mod):
    assert not mod.is_addressed(
        pr_closed=False,
        thread_resolved=False,
        item_created_at=T0,
        bot_commit_at=None,
        bot_comment_at=None,
    )


# ---------------------------------------------------------------------------
# determine_warning_stage — boundaries
# ---------------------------------------------------------------------------


def test_stage_none_just_before_warn(mod):
    now = T0 + timedelta(hours=2) - timedelta(seconds=1)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=None,
            escalated_at=None,
        )
        == "none"
    )


def test_stage_warn_just_after_warn_threshold(mod):
    now = T0 + timedelta(hours=2)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=None,
            escalated_at=None,
        )
        == "warn"
    )


def test_stage_rewarn_suppressed_within_interval(mod):
    last = T0 + timedelta(hours=2)
    now = last + timedelta(hours=4) - timedelta(seconds=1)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=last,
            escalated_at=None,
        )
        == "none"
    )


def test_stage_rewarn_after_interval(mod):
    last = T0 + timedelta(hours=2)
    now = last + timedelta(hours=4)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=last,
            escalated_at=None,
        )
        == "rewarn"
    )


def test_stage_escalate_first_time(mod):
    now = T0 + timedelta(hours=8)
    last = T0 + timedelta(hours=2)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=last,
            escalated_at=None,
        )
        == "escalate"
    )


def test_stage_escalate_once_suppressed(mod):
    """Escalated recently → no re-escalate even if age > 8h; rewarn may still apply."""
    now = T0 + timedelta(hours=10)
    last_warned = T0 + timedelta(hours=9)  # within rewarn window
    escalated_at = T0 + timedelta(hours=8)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=last_warned,
            escalated_at=escalated_at,
        )
        == "none"
    )


def test_stage_escalate_again_after_interval(mod):
    now = T0 + timedelta(hours=16)
    last_warned = T0 + timedelta(hours=14)
    escalated_at = T0 + timedelta(hours=8)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=last_warned,
            escalated_at=escalated_at,
        )
        == "escalate"
    )


def test_stage_custom_thresholds(mod):
    now = T0 + timedelta(hours=1)
    assert (
        mod.determine_warning_stage(
            item_created_at=T0,
            now=now,
            last_warned=None,
            escalated_at=None,
            warn_hours=0.5,
            rewarn_hours=1.0,
            escalate_hours=24.0,
        )
        == "warn"
    )


# ---------------------------------------------------------------------------
# FIX_REQUEST_PATTERN
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,expect",
    [
        ("ここを修正してください", True),
        ("Please fix this", True),
        ("looks good to me", False),
        ("CHANGE the name", True),
        ("対応してください", True),
        ("お願いします", True),
        ("直してほしい", True),
        ("required change", True),
        ("address the edge case", True),
    ],
)
def test_fix_request_pattern(mod, body, expect):
    matched = mod.FIX_REQUEST_PATTERN.search(body) is not None
    assert matched is expect


# ---------------------------------------------------------------------------
# dry-run send
# ---------------------------------------------------------------------------


def test_dry_run_send_does_not_call_messenger(mod, monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "DRY_RUN", True)
    monkeypatch.setattr(mod, "LOG_FILE", tmp_path / "dispatch.log")
    mod.LOG_FILE.write_text("", encoding="utf-8")
    mod.send("rin", "【警告】test body")
    log_text = mod.LOG_FILE.read_text(encoding="utf-8")
    assert "DRY_RUN send -> rin" in log_text


def test_parse_gh_time_zulu(mod):
    dt = mod.parse_gh_time("2026-07-01T12:00:00Z")
    assert dt == T0
