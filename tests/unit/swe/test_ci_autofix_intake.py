from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from swe.ci_autofix_intake import (
    CIAutofixIntakeStore,
    IntakeRule,
    extract_actions_run_ids,
    poll_gmail_for_candidates,
)


def test_extract_actions_run_ids_deduplicates() -> None:
    text = """
    https://github.com/cmnt1/animaworks/actions/runs/123
    duplicate: https://github.com/cmnt1/animaworks/actions/runs/123
    markdown path actions/runs/456
    """

    assert extract_actions_run_ids(text) == ["123", "456"]


def test_store_upsert_candidate_records_event(tmp_path: Path) -> None:
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")

    job, created = store.upsert_candidate(
        run_id="123",
        repo="cmnt1/animaworks",
        branch="main",
        actor="cmnt1",
        source_message_id="m1",
        subject="CI failed",
        run_url="https://github.com/cmnt1/animaworks/actions/runs/123",
    )
    duplicate, duplicate_created = store.upsert_candidate(
        run_id="123",
        repo="cmnt1/animaworks",
        branch="main",
        actor="cmnt1",
        source_message_id="m1",
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == job.id
    assert store.list_jobs()[0].run_id == "123"
    assert store.list_jobs()[0].last_run_id == "123"
    assert store.list_jobs()[0].attempt_count == 0
    assert store.list_jobs()[0].max_attempts == 10
    assert store.list_events(job.id)[0].message == "candidate created"


def test_store_upsert_candidate_preserves_followup_run_state(tmp_path: Path) -> None:
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    job, _ = store.upsert_candidate(
        run_id="100",
        repo="cmnt1/animaworks",
        branch="main",
        actor="cmnt1",
        run_url="https://github.com/cmnt1/animaworks/actions/runs/100",
    )
    store.update_job_state(
        job.id,
        status="waiting_ci",
        last_run_id="101",
        run_url="https://github.com/cmnt1/animaworks/actions/runs/101",
        last_commit="abcdef1234567890",
    )

    duplicate, created = store.upsert_candidate(
        run_id="100",
        repo="cmnt1/animaworks",
        branch="main",
        actor="cmnt1",
        source_message_id="m1",
        source_date="2099-07-05T04:17:40Z",
        subject="Run failed",
        run_url="https://github.com/cmnt1/animaworks/actions/runs/100",
    )

    assert created is False
    assert duplicate.id == job.id
    assert duplicate.last_run_id == "101"
    assert duplicate.run_url == "https://github.com/cmnt1/animaworks/actions/runs/101"
    assert duplicate.to_dict()["phase"] == "ci_waiting"
    assert "commit abcdef123456" in duplicate.to_dict()["phase_detail"]


def test_completed_jobs_are_hidden_from_default_list_but_counted(tmp_path: Path) -> None:
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    job, _ = store.upsert_candidate(
        run_id="124",
        repo="cmnt1/animaworks",
        branch="main",
        actor="cmnt1",
        source_message_id="m2",
        subject="CI fixed",
        run_url="https://github.com/cmnt1/animaworks/actions/runs/124",
    )

    store.update_job_state(job.id, status="completed", last_conclusion="success", terminal_reason="CI passed")
    summary = store.summary()

    assert store.list_jobs() == []
    assert store.list_jobs(include_terminal=True)[0].id == job.id
    assert summary["active_count"] == 0
    assert summary["completed_count"] == 1
    assert summary["latest_completed"]["id"] == job.id


@dataclass
class FakeEmail:
    id: str
    subject: str
    snippet: str
    date: str = "Sat, 05 Jul 2099 13:17:40 +0900"


class FakeGmail:
    def __init__(self) -> None:
        self.query = ""

    def search_emails(self, query: str, max_results: int = 20):
        self.query = query
        return [FakeEmail("m1", "Run failed", "see actions/runs/789")]

    def get_email_body(self, message_id: str) -> str:
        return "https://github.com/cmnt1/animaworks/actions/runs/789"


def test_poll_gmail_for_candidates_creates_jobs(tmp_path: Path) -> None:
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    gmail = FakeGmail()

    result = poll_gmail_for_candidates(
        store=store,
        rule=IntakeRule(query="from:notifications@github.com", max_results=5),
        gmail_client=gmail,
    )

    assert result["ok"] is True
    assert result["checked"] == 1
    assert result["created"][0]["run_id"] == "789"
    assert store.list_jobs()[0].source_message_id == "m1"
    assert store.list_jobs()[0].source_date == "2099-07-05T04:17:40Z"
    assert gmail.query == "from:notifications@github.com"


def test_poll_gmail_uses_first_run_id_from_a_message(tmp_path: Path) -> None:
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")

    class MultiRunGmail(FakeGmail):
        def search_emails(self, query: str, max_results: int = 20):
            self.query = query
            return [FakeEmail("m2", "Run failed", "see actions/runs/111 and actions/runs/222")]

        def get_email_body(self, message_id: str) -> str:
            return "\n".join(
                [
                    "https://github.com/cmnt1/animaworks/actions/runs/111",
                    "https://github.com/cmnt1/animaworks/actions/runs/222",
                ]
            )

    result = poll_gmail_for_candidates(
        store=store,
        rule=IntakeRule(query="from:notifications@github.com", max_results=5),
        gmail_client=MultiRunGmail(),
    )

    jobs = store.list_jobs()
    events = store.list_events(jobs[0].id)
    assert len(jobs) == 1
    assert result["created"][0]["run_id"] == "111"
    assert jobs[0].last_run_id == "111"
    assert events[-1].data["ignored_run_ids"] == ["222"]


def test_poll_gmail_links_followup_run_to_active_job(tmp_path: Path) -> None:
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    first, _ = store.upsert_candidate(
        run_id="100",
        repo="cmnt1/animaworks",
        branch="main",
        actor="cmnt1",
        run_url="https://github.com/cmnt1/animaworks/actions/runs/100",
    )
    store.update_job_state(first.id, status="waiting_ci", automation_enabled=True)

    class FollowupGmail(FakeGmail):
        def search_emails(self, query: str, max_results: int = 20):
            self.query = query
            return [FakeEmail("m2", "Run failed again", "see actions/runs/101")]

        def get_email_body(self, message_id: str) -> str:
            return "https://github.com/cmnt1/animaworks/actions/runs/101"

    result = poll_gmail_for_candidates(
        store=store,
        rule=IntakeRule(query="from:notifications@github.com", max_results=5),
        gmail_client=FollowupGmail(),
    )

    jobs = store.list_jobs()
    assert len(jobs) == 1
    assert result["created"] == []
    assert result["linked"][0]["id"] == first.id
    assert jobs[0].run_id == "100"
    assert jobs[0].last_run_id == "101"
    assert jobs[0].status == "waiting_ci"
    assert any(event.message == "follow-up CI run linked" for event in store.list_events(first.id))


def test_poll_gmail_does_not_link_old_mail_to_active_job(tmp_path: Path) -> None:
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    first, _ = store.upsert_candidate(
        run_id="100",
        repo="cmnt1/animaworks",
        branch="main",
        actor="cmnt1",
        run_url="https://github.com/cmnt1/animaworks/actions/runs/100",
    )
    store.update_job_state(first.id, status="waiting_ci", automation_enabled=True)

    class OldFollowupGmail(FakeGmail):
        def search_emails(self, query: str, max_results: int = 20):
            self.query = query
            return [FakeEmail("m-old", "Run failed earlier", "see actions/runs/99", "Sat, 05 Jul 2000 13:17:40 +0900")]

        def get_email_body(self, message_id: str) -> str:
            return "https://github.com/cmnt1/animaworks/actions/runs/99"

    result = poll_gmail_for_candidates(
        store=store,
        rule=IntakeRule(query="from:notifications@github.com", max_results=5),
        gmail_client=OldFollowupGmail(),
    )

    jobs = store.list_jobs(include_terminal=True)
    assert result["linked"] == []
    assert result["created"] == []
    assert result["stale"][0]["run_id"] == "99"
    assert {job.run_id: job.last_run_id for job in jobs} == {"100": "100"}


def _incident(store, run_id="100"):
    return store.upsert_candidate(run_id=run_id, repo="cmnt1/animaworks", branch="main", actor="cmnt1")[0]


class FollowupMail(FakeGmail):
    def search_emails(self, query, max_results=20):
        return [FakeEmail("followup", "Run failed", "actions/runs/101")]

    def get_email_body(self, message_id):
        return "https://github.com/cmnt1/animaworks/actions/runs/101"


def test_current_and_historical_run_notifications_return_same_incident(tmp_path):
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    first = _incident(store)
    for current in ("101", "102"):
        store.update_job_state(first.id, status="waiting_ci", automation_enabled=True, last_run_id=current)
        result = poll_gmail_for_candidates(store=store, rule=IntakeRule(), gmail_client=FollowupMail())
        assert result["created"] == []
        assert result["existing"][0]["id"] == first.id
        assert store.get_job(first.id).last_run_id == current
    assert len(store.list_jobs(include_terminal=True)) == 1
    duplicate, created = store.upsert_candidate(run_id="101", repo=first.repo, branch=first.branch, actor=first.actor)
    assert not created and duplicate.id == first.id


def test_mail_link_is_remembered_without_overwriting_running_attempt(tmp_path):
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    first = _incident(store)
    store.reserve_attempt(first.id)
    store.begin_attempt(first.id)
    for _ in range(2):
        result = poll_gmail_for_candidates(store=store, rule=IntakeRule(), gmail_client=FollowupMail())
        assert result["created"] == []
        assert store.get_job(first.id).status == "running"
        assert store.get_job(first.id).last_run_id == "100"
    assert store.find_job_for_run(repo=first.repo, run_id="101").id == first.id


def test_resolved_incident_is_not_recreated_by_late_mail(tmp_path):
    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    first = _incident(store)
    store.update_job_state(first.id, status="completed", last_run_id="101")
    other = _incident(store, "200")
    result = poll_gmail_for_candidates(store=store, rule=IntakeRule(), gmail_client=FollowupMail())
    assert result["created"] == []
    assert result["existing"][0]["id"] == first.id
    assert store.get_job(other.id).last_run_id == "200"
    assert store.get_job(first.id).status == "completed"


def test_legacy_history_migration_merges_only_unstarted_duplicates(tmp_path):
    path = tmp_path / "ci.sqlite3"
    store = CIAutofixIntakeStore(path)
    first = _incident(store)
    store.update_job_state(first.id, status="waiting_ci", automation_enabled=True, last_run_id="102")
    store.add_event(first.id, "info", "GitHub Actions run inspected", {"run_id": "101"})
    with store._connect() as con:
        cur = con.execute(
            "INSERT INTO ci_autofix_jobs(run_id,repo,branch,actor,status,created_at,updated_at) "
            "VALUES ('101','cmnt1/animaworks','main','cmnt1','candidate','2099-01-01','2099-01-01')"
        )
        duplicate_id = cur.lastrowid
        con.execute("DROP TABLE ci_autofix_run_jobs")
    migrated = CIAutofixIntakeStore(path)
    assert migrated.find_job_for_run(repo=first.repo, run_id="101").id == first.id
    assert migrated.dismiss_duplicate_candidates() == [duplicate_id]
    assert migrated.dismiss_duplicate_candidates() == []
    assert migrated.get_job(duplicate_id).status == "dismissed"
    assert str(first.id) in migrated.get_job(duplicate_id).terminal_reason
    assert migrated.get_job(first.id).status == "waiting_ci"
    assert migrated.list_events(duplicate_id)[-1].data["owner_job_id"] == first.id


def test_parallel_duplicate_intake_creates_one_job(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = CIAutofixIntakeStore(tmp_path / "ci.sqlite3")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.upsert_candidate(
            run_id="101", repo="cmnt1/animaworks", branch="main", actor="cmnt1"), range(4)))
    assert sum(created for _, created in results) == 1
    assert len({job.id for job, _ in results}) == 1
