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
    assert store.list_jobs()[0].max_attempts == 5
    assert store.list_events(job.id)[0].message == "candidate created"


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
    assert jobs[0].status == "ci_failed"
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
