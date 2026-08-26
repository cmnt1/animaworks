"""check_conflicts() のユニットテスト（scripts/pr-review-dispatch.py）。"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "pr-review-dispatch.py"


def _pr(
    number: int,
    mergeable: str,
    sha: str = "a" * 40,
    *,
    draft: bool = False,
    title: str = "t",
) -> dict:
    return {
        "number": number,
        "title": title,
        "headRefName": f"feat/{number}",
        "baseRefName": "main",
        "headRefOid": sha,
        "mergeable": mergeable,
        "isDraft": draft,
    }


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_SHARED_DIR", str(tmp_path))
    monkeypatch.setenv("PR_DISPATCH_REPOS", "o/r")
    spec = importlib.util.spec_from_file_location("pr_review_dispatch_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPOS = ["o/r"]
    module.sent_messages = []
    module.send = lambda target, content: module.sent_messages.append((target, content))
    return module


def _run(mod, state: dict, prs: list[dict]) -> list[dict]:
    tasks: list[dict] = []
    mod.gh = lambda args: json.dumps(prs)
    mod.dispatch_task = lambda **kwargs: tasks.append(kwargs) or True
    mod.check_conflicts(state)
    return tasks


def test_conflicting_pr_notifies_once(mod):
    state = mod.default_state()
    sent = _run(mod, state, [_pr(1, "CONFLICTING")])
    assert len(sent) == 1
    assert sent[0]["target"] == "natsume"
    assert sent[0]["task_id"] == "gh-conflict-o-r#1-aaaaaaaa"
    assert "procedures/pr-conflict-resolution.md" in sent[0]["instruction"]
    # 同一headのままの再巡回では再通知しない
    assert _run(mod, state, [_pr(1, "CONFLICTING")]) == []


def test_conflicting_pr_reminds_rin_on_every_scan(mod):
    state = mod.default_state()

    _run(mod, state, [_pr(1, "CONFLICTING")])
    _run(mod, state, [_pr(1, "CONFLICTING")])

    assert len(mod.sent_messages) == 2
    assert all(target == "rin" for target, _content in mod.sent_messages)
    assert all("マージコンフリクト継続検知" in content for _target, content in mod.sent_messages)


def test_new_head_still_conflicting_renotifies(mod):
    state = mod.default_state()
    _run(mod, state, [_pr(1, "CONFLICTING", sha="a" * 40)])
    sent = _run(mod, state, [_pr(1, "CONFLICTING", sha="b" * 40)])
    assert len(sent) == 1


def test_mergeable_clears_record_and_reconflict_renotifies(mod):
    state = mod.default_state()
    _run(mod, state, [_pr(1, "CONFLICTING")])
    _run(mod, state, [_pr(1, "MERGEABLE")])
    assert state["conflict_notified"] == {}
    # baseが進んで同一headが再びCONFLICTINGになったら再通知する
    sent = _run(mod, state, [_pr(1, "CONFLICTING")])
    assert len(sent) == 1


def test_unknown_and_draft_are_skipped(mod):
    state = mod.default_state()
    assert _run(mod, state, [_pr(1, "UNKNOWN"), _pr(2, "CONFLICTING", draft=True)]) == []
    assert state["conflict_notified"] == {}


def test_closed_pr_record_is_pruned(mod):
    state = mod.default_state()
    _run(mod, state, [_pr(1, "CONFLICTING")])
    assert "o/r#1" in state["conflict_notified"]
    _run(mod, state, [])
    assert state["conflict_notified"] == {}


def _terminal_task(task_id: str, status: str) -> SimpleNamespace:
    # updated_at far in the past so the redispatch cooldown does not interfere
    return SimpleNamespace(task_id=task_id, status=status, updated_at="2026-08-01T00:00:00Z")


def test_failed_dispatch_latches_reopen_twice_then_stop(mod, monkeypatch):
    ci_key = "o/r#1_aaaaaaaa"
    conflict_key = "o/r#2"
    state = mod.default_state()
    state["ci_notified"][ci_key] = "2026-08-11T00:00:00Z"
    state["conflict_notified"][conflict_key] = "bbbbbbbb"
    monkeypatch.setattr(mod, "_direct_task", lambda task_id: _terminal_task(task_id, "failed"))

    for retry in (1, 2):
        mod.reopen_stalled_dispatches(state)
        assert ci_key not in state["ci_notified"]
        assert conflict_key not in state["conflict_notified"]
        assert set(state["failed_task_retries"].values()) == {retry}
        state["ci_notified"][ci_key] = "2026-08-11T00:00:00Z"
        state["conflict_notified"][conflict_key] = "bbbbbbbb"

    mod.reopen_stalled_dispatches(state)
    assert ci_key in state["ci_notified"]
    assert conflict_key in state["conflict_notified"]
    assert set(state["failed_task_retries"].values()) == {2}


@pytest.mark.parametrize("status", ["pending", "in_progress", "waiting"])
def test_active_dispatch_keeps_latch(mod, monkeypatch, status):
    state = mod.default_state()
    state["ci_notified"]["o/r#1_aaaaaaaa"] = "2026-08-11T00:00:00Z"
    monkeypatch.setattr(mod, "_direct_task", lambda task_id: _terminal_task(task_id, status))

    mod.reopen_stalled_dispatches(state)

    assert "o/r#1_aaaaaaaa" in state["ci_notified"]
    assert state["failed_task_retries"] == {}


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_done_and_cancelled_reopen_latch_with_context(mod, monkeypatch, status):
    """done/cancelled でも問題が現存する限り再投入対象（done≠解決）。"""
    state = mod.default_state()
    state["ci_notified"]["o/r#1_aaaaaaaa"] = "2026-08-11T00:00:00Z"
    monkeypatch.setattr(mod, "_direct_task", lambda task_id: _terminal_task(task_id, status))

    mod.reopen_stalled_dispatches(state)

    assert "o/r#1_aaaaaaaa" not in state["ci_notified"]
    base_id = mod._ci_task_id("o/r", 1, "aaaaaaaa")
    assert state["failed_task_retries"][base_id] == 1
    assert state["retry_context"][base_id]["last_status"] == status
    preamble = mod._whiff_preamble(base_id, state)
    assert "空振り" in preamble
    if status == "done":
        assert "宣言と現実が食い違っている" in preamble


def test_recent_terminal_task_waits_for_cooldown(mod, monkeypatch):
    state = mod.default_state()
    state["ci_notified"]["o/r#1_aaaaaaaa"] = "2026-08-11T00:00:00Z"
    fresh = mod.iso(mod.now_utc())
    monkeypatch.setattr(
        mod,
        "_direct_task",
        lambda task_id: SimpleNamespace(task_id=task_id, status="done", updated_at=fresh),
    )

    mod.reopen_stalled_dispatches(state)

    assert "o/r#1_aaaaaaaa" in state["ci_notified"]
    assert state["failed_task_retries"] == {}
