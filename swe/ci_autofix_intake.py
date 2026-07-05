"""Gmail-backed intake primitives for CI auto-fix jobs."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

RUN_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/actions/runs/(?P<run_id>\d+)",
    re.IGNORECASE,
)
RUN_ID_RE = re.compile(r"actions/runs/(?P<run_id>\d+)", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def extract_actions_run_ids(text: str) -> list[str]:
    """Extract unique GitHub Actions run IDs from email snippets or bodies."""

    seen: set[str] = set()
    found: list[str] = []
    for match in RUN_URL_RE.finditer(text):
        run_id = match.group("run_id")
        if run_id not in seen:
            seen.add(run_id)
            found.append(run_id)
    for match in RUN_ID_RE.finditer(text):
        run_id = match.group("run_id")
        if run_id not in seen:
            seen.add(run_id)
            found.append(run_id)
    return found


def default_failure_mail_query(repo: str = "cmnt1/animaworks", days: int = 14) -> str:
    owner, name = repo.split("/", 1)
    return (
        "from:notifications@github.com "
        f'("{owner}/{name}" OR "{name}") '
        '(failed OR failure OR "Run failed" OR "workflow run") '
        f"newer_than:{days}d"
    )


@dataclass(frozen=True)
class IntakeRule:
    repo: str = "cmnt1/animaworks"
    branch: str = "main"
    actor: str = "cmnt1"
    query: str = ""
    max_results: int = 20
    dry_run: bool = True
    llm_provider: str = "claude_code"
    llm_model: str = ""

    def resolved_query(self) -> str:
        return self.query or default_failure_mail_query(self.repo)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["query"] = self.resolved_query()
        return data


@dataclass(frozen=True)
class IntakeJob:
    id: int
    run_id: str
    repo: str
    branch: str
    actor: str
    status: str
    source_message_id: str
    subject: str
    run_url: str
    dry_run: bool
    llm_provider: str
    llm_model: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IntakeEvent:
    id: int
    job_id: int
    ts: str
    level: str
    message: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GmailLike(Protocol):
    def search_emails(self, query: str, max_results: int = 20) -> Iterable[Any]: ...

    def get_email_body(self, message_id: str) -> str: ...


class CIAutofixIntakeStore:
    """Small SQLite store for CI auto-fix intake jobs and event logs."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ci_autofix_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    repo TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_message_id TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '',
                    run_url TEXT NOT NULL DEFAULT '',
                    dry_run INTEGER NOT NULL DEFAULT 1,
                    llm_provider TEXT NOT NULL DEFAULT 'claude_code',
                    llm_model TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in con.execute("PRAGMA table_info(ci_autofix_jobs)").fetchall()}
            if "llm_provider" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN llm_provider TEXT NOT NULL DEFAULT 'claude_code'")
            if "llm_model" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN llm_model TEXT NOT NULL DEFAULT ''")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ci_autofix_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    ts TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(job_id) REFERENCES ci_autofix_jobs(id)
                )
                """
            )

    def upsert_candidate(
        self,
        *,
        run_id: str,
        repo: str,
        branch: str,
        actor: str,
        source_message_id: str = "",
        subject: str = "",
        run_url: str = "",
        dry_run: bool = True,
        llm_provider: str = "claude_code",
        llm_model: str = "",
    ) -> tuple[IntakeJob, bool]:
        now = utc_now()
        with self._connect() as con:
            row = con.execute("SELECT * FROM ci_autofix_jobs WHERE run_id = ?", (run_id,)).fetchone()
            if row:
                con.execute(
                    """
                    UPDATE ci_autofix_jobs
                    SET source_message_id = COALESCE(NULLIF(?, ''), source_message_id),
                        subject = COALESCE(NULLIF(?, ''), subject),
                        run_url = COALESCE(NULLIF(?, ''), run_url),
                        llm_provider = COALESCE(NULLIF(?, ''), llm_provider),
                        llm_model = COALESCE(NULLIF(?, ''), llm_model),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (source_message_id, subject, run_url, llm_provider, llm_model, now, row["id"]),
                )
                updated = con.execute("SELECT * FROM ci_autofix_jobs WHERE id = ?", (row["id"],)).fetchone()
                assert updated is not None
                return self._job_from_row(updated), False

            cur = con.execute(
                """
                INSERT INTO ci_autofix_jobs
                    (run_id, repo, branch, actor, status, source_message_id, subject, run_url, dry_run, llm_provider, llm_model, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo,
                    branch,
                    actor,
                    "candidate",
                    source_message_id,
                    subject,
                    run_url,
                    1 if dry_run else 0,
                    llm_provider,
                    llm_model,
                    now,
                    now,
                ),
            )
            row = con.execute("SELECT * FROM ci_autofix_jobs WHERE id = ?", (cur.lastrowid,)).fetchone()
            assert row is not None
            job = self._job_from_row(row)
        self.add_event(job.id, "info", "candidate created", {"run_id": run_id, "repo": repo})
        return job, True

    def list_jobs(self, limit: int = 50) -> list[IntakeJob]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM ci_autofix_jobs ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        terminal = {"completed", "dismissed", "failed", "exhausted"}
        jobs = self.list_jobs(limit=100)
        active = [job for job in jobs if job.status not in terminal]
        latest = active[0] if active else (jobs[0] if jobs else None)
        return {
            "active_count": len(active),
            "total_count": len(jobs),
            "latest": latest.to_dict() if latest else None,
        }

    def get_job(self, job_id: int) -> IntakeJob:
        with self._connect() as con:
            row = con.execute("SELECT * FROM ci_autofix_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._job_from_row(row)

    def add_event(self, job_id: int, level: str, message: str, data: dict[str, Any] | None = None) -> IntakeEvent:
        payload = json.dumps(data or {}, ensure_ascii=False)
        ts = utc_now()
        with self._connect() as con:
            cur = con.execute(
                """
                INSERT INTO ci_autofix_events (job_id, ts, level, message, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, ts, level, message, payload),
            )
            con.execute("UPDATE ci_autofix_jobs SET updated_at = ? WHERE id = ?", (ts, job_id))
            row = con.execute("SELECT * FROM ci_autofix_events WHERE id = ?", (cur.lastrowid,)).fetchone()
        assert row is not None
        return self._event_from_row(row)

    def list_events(self, job_id: int, limit: int = 200) -> list[IntakeEvent]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM ci_autofix_events
                WHERE job_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        return [self._event_from_row(row) for row in reversed(rows)]

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> IntakeJob:
        return IntakeJob(
            id=int(row["id"]),
            run_id=str(row["run_id"]),
            repo=str(row["repo"]),
            branch=str(row["branch"]),
            actor=str(row["actor"]),
            status=str(row["status"]),
            source_message_id=str(row["source_message_id"]),
            subject=str(row["subject"]),
            run_url=str(row["run_url"]),
            dry_run=bool(row["dry_run"]),
            llm_provider=str(row["llm_provider"]),
            llm_model=str(row["llm_model"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> IntakeEvent:
        return IntakeEvent(
            id=int(row["id"]),
            job_id=int(row["job_id"]),
            ts=str(row["ts"]),
            level=str(row["level"]),
            message=str(row["message"]),
            data=json.loads(str(row["data_json"] or "{}")),
        )


def poll_gmail_for_candidates(
    *,
    store: CIAutofixIntakeStore,
    rule: IntakeRule,
    gmail_client: GmailLike | None = None,
) -> dict[str, Any]:
    """Search Gmail for GitHub failure messages and create candidate jobs."""

    if gmail_client is None:
        from core.tools.gmail import GmailClient

        gmail_client = GmailClient()

    query = rule.resolved_query()
    messages = list(gmail_client.search_emails(query=query, max_results=rule.max_results))
    created: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []

    for message in messages:
        message_id = str(getattr(message, "id", "") or "")
        subject = str(getattr(message, "subject", "") or "")
        snippet = str(getattr(message, "snippet", "") or "")
        body = gmail_client.get_email_body(message_id) if message_id else ""
        text = "\n".join([subject, snippet, body])
        for run_id in extract_actions_run_ids(text):
            run_url = f"https://github.com/{rule.repo}/actions/runs/{run_id}"
            job, was_created = store.upsert_candidate(
                run_id=run_id,
                repo=rule.repo,
                branch=rule.branch,
                actor=rule.actor,
                source_message_id=message_id,
                subject=subject,
                run_url=run_url,
                dry_run=rule.dry_run,
                llm_provider=rule.llm_provider,
                llm_model=rule.llm_model,
            )
            store.add_event(
                job.id,
                "info",
                "gmail message matched",
                {"message_id": message_id, "subject": subject, "query": query},
            )
            (created if was_created else existing).append(job.to_dict())

    return {
        "ok": True,
        "query": query,
        "checked": len(messages),
        "created": created,
        "existing": existing,
    }
