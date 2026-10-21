from types import SimpleNamespace

import pytest

from scripts import ci_autofix_agent_attempt as agent
from swe.ci_autofix_intake import CIAutofixIntakeStore


def make_job(store, run_id="100"):
    return store.upsert_candidate(run_id=run_id, repo="cmnt1/animaworks", branch="main", actor="cmnt1")[0]


@pytest.mark.parametrize("conclusion,status,expected", [
    ("success", "completed", "completed"),
    ("", "in_progress", "waiting_ci"),
    ("failure", "completed", "needs_attention"),
])
def test_no_push_uses_verified_ci_not_agent_report(tmp_path, conclusion, status, expected):
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    job = make_job(store)
    run = dict(databaseId=102, headSha="a" * 40, status=status, conclusion=conclusion)
    assert agent._record_existing_ci(store, job, run) == expected
    updated = store.get_job(job.id)
    assert updated.status == expected
    assert updated.last_commit == "a" * 40
    assert updated.last_run_id == "102"
    assert updated.automation_enabled == (expected == "waiting_ci")
    assert store.find_job_for_run(repo=job.repo, run_id="102").id == job.id
    if expected == "needs_attention":
        assert "CIも失敗" in updated.terminal_reason
    if expected == "waiting_ci":
        assert store.latest_event(job.id, ("LLM agent attempt finished; waiting for next CI result",))


def test_no_push_does_not_restart_another_incident(tmp_path):
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    owner = make_job(store)
    store.update_job_state(owner.id, status="exhausted", last_run_id="102")
    duplicate = make_job(store, "101")
    run = dict(databaseId=102, headSha="b" * 40, status="completed", conclusion="failure")
    assert agent._record_existing_ci(store, duplicate, run) == "dismissed"
    assert store.get_job(owner.id).status == "exhausted"
    assert store.get_job(duplicate.id).status == "dismissed"
    assert str(owner.id) in store.get_job(duplicate.id).terminal_reason


def test_ci_lookup_filters_commit_and_branch_and_uses_latest_run(monkeypatch, tmp_path):
    import json

    head = "c" * 40
    calls = []
    runs = [
        dict(databaseId=1, headSha="d" * 40, headBranch="main", createdAt="2099-01-03"),
        dict(databaseId=2, headSha=head, headBranch="other", createdAt="2099-01-03"),
        dict(databaseId=3, headSha=head, headBranch="main", createdAt="2099-01-01"),
        dict(databaseId=4, headSha=head, headBranch="main", createdAt="2099-01-02"),
    ]

    def execute(args, **kwargs):
        calls.append(args)
        output = (head if args[0] == "git" else
                  json.dumps({"workflowName": "CI"}) if args[2] == "view" else json.dumps(runs))
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(agent.subprocess, "run", execute)
    job = SimpleNamespace(repo="cmnt1/animaworks", branch="main", last_run_id="100")
    assert agent._current_head_ci(tmp_path, job)["databaseId"] == 4
    assert "CI" in calls[-1] and head in calls[-1] and job.repo in calls[-1]
