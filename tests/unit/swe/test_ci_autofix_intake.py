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
    assert store.list_events(job.id)[0].message == "candidate created"


@dataclass
class FakeEmail:
    id: str
    subject: str
    snippet: str


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
    assert gmail.query == "from:notifications@github.com"
