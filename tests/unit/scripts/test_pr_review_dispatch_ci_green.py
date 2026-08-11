"""check_ci() のCI全green再通知のユニットテスト（scripts/pr-review-dispatch.py）。"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "pr-review-dispatch.py"

SHA = "a" * 40


def _pr(number: int, rollup: list[dict], sha: str = SHA) -> dict:
    return {"number": number, "headRefOid": sha, "statusCheckRollup": rollup}


def _green_run(name: str = "unit") -> dict:
    return {"name": name, "status": "COMPLETED", "conclusion": "SUCCESS"}


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_SHARED_DIR", str(tmp_path))
    monkeypatch.setenv("PR_DISPATCH_REPOS", "o/r")
    spec = importlib.util.spec_from_file_location("pr_review_dispatch_ci_green_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPOS = ["o/r"]
    return module


def _run(mod, state: dict, prs: list[dict]) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    mod.gh = lambda args: json.dumps(prs)
    mod.send = lambda to, content: sent.append((to, content))
    mod.dispatch_task = lambda **kwargs: True
    mod.check_ci(state)
    return sent


def test_ci_all_green_mixed_rollup(mod):
    assert mod.ci_all_green([_green_run(), {"context": "lint", "state": "SUCCESS"}])
    assert not mod.ci_all_green([])
    assert not mod.ci_all_green([{"name": "x", "status": "IN_PROGRESS", "conclusion": ""}])
    assert not mod.ci_all_green([{"context": "lint", "state": "PENDING"}])
    assert mod.ci_all_green([{"name": "x", "status": "COMPLETED", "conclusion": "SKIPPED"}])


def test_green_notifies_reviewer_once_for_dispatched_head(mod):
    state = mod.default_state()
    state["prs"]["o/r#1"] = {"sha": SHA, "notified_sha": SHA, "title": "t"}
    sent = _run(mod, state, [_pr(1, [_green_run()])])
    assert len(sent) == 1
    assert sent[0][0] == mod.REVIEWER
    assert "o/r#1" in sent[0][1]
    # 同一SHAの再巡回では再通知しない
    assert _run(mod, state, [_pr(1, [_green_run()])]) == []


def test_green_skips_undispatched_or_pending(mod):
    state = mod.default_state()
    # review未通知のHEADは対象外（check_commitsの通常経路に任せる）
    state["prs"]["o/r#1"] = {"sha": SHA, "notified_sha": "", "title": "t"}
    assert _run(mod, state, [_pr(1, [_green_run()])]) == []
    # 実行中チェックが残っていれば通知しない
    state["prs"]["o/r#2"] = {"sha": SHA, "notified_sha": SHA, "title": "t"}
    pending = [_green_run(), {"name": "e2e", "status": "IN_PROGRESS", "conclusion": ""}]
    assert _run(mod, state, [_pr(2, pending)]) == []


def test_green_skips_approved_pr(mod):
    state = mod.default_state()
    state["prs"]["o/r#1"] = {"sha": SHA, "notified_sha": SHA, "title": "t"}
    pr = _pr(1, [_green_run()])
    pr["reviewDecision"] = "APPROVED"
    assert _run(mod, state, [pr]) == []


def test_failing_pr_goes_to_fixer_not_green(mod):
    state = mod.default_state()
    state["prs"]["o/r#1"] = {"sha": SHA, "notified_sha": SHA, "title": "t"}
    rollup = [{"name": "unit", "status": "COMPLETED", "conclusion": "FAILURE"}]
    assert _run(mod, state, [_pr(1, rollup)]) == []
