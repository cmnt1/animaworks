"""Gmail-backed intake primitives for CI auto-fix jobs."""

from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol

RUN_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/actions/runs/(?P<run_id>\d+)",
    re.IGNORECASE,
)
RUN_ID_RE = re.compile(r"actions/runs/(?P<run_id>\d+)", re.IGNORECASE)
TERMINAL_STATUSES = frozenset({"completed", "dismissed", "failed", "exhausted"})
ACTIVE_STATUSES = frozenset({"candidate", "queued", "running", "waiting_ci", "ci_failed", "needs_attention"})
READONLY_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GENERAL_GMAIL_CONFIG_PATH = Path(r"E:\OneDriveBiz\Tools\General\py_mod\intake\gmail_config.json")
GENERAL_GMAIL_TOKEN_PATH = Path(r"E:\OneDriveBiz\Claude\.credentials\google_oauth_token.json")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_mail_date(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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


def default_failure_mail_query(repo: str = "cmnt1/animaworks", days: int = 1) -> str:
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
    root_run_id: str
    last_run_id: str
    repo: str
    branch: str
    actor: str
    status: str
    source_message_id: str
    source_date: str
    subject: str
    run_url: str
    dry_run: bool
    llm_provider: str
    llm_model: str
    attempt_count: int
    max_attempts: int
    automation_enabled: bool
    next_poll_at: str
    last_commit: str
    last_conclusion: str
    terminal_reason: str
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


@dataclass(frozen=True)
class _ReadonlyEmail:
    id: str
    thread_id: str
    from_addr: str
    subject: str
    snippet: str
    date: str = ""


class _ReadonlyGmailClient:
    """Gmail search client for CI intake, scoped to read-only access."""

    def __init__(self, token_path: Path):
        self.token_path = token_path
        self._service = None

    @property
    def service(self):
        if self._service is None:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(str(self.token_path), READONLY_GMAIL_SCOPES)
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    self.token_path.write_text(creds.to_json(), encoding="utf-8")
                else:
                    raise RuntimeError(f"Google OAuth token is invalid: {self.token_path}")
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def search_emails(self, query: str, max_results: int = 20) -> list[_ReadonlyEmail]:
        result = self.service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        emails: list[_ReadonlyEmail] = []
        for msg in result.get("messages", []):
            message = (
                self.service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
            emails.append(
                _ReadonlyEmail(
                    id=str(message.get("id") or ""),
                    thread_id=str(message.get("threadId") or ""),
                    from_addr=str(headers.get("From") or ""),
                    subject=str(headers.get("Subject") or ""),
                    snippet=str(message.get("snippet") or ""),
                    date=str(headers.get("Date") or ""),
                )
            )
        return emails

    def get_email_body(self, message_id: str) -> str:
        message = self.service.users().messages().get(userId="me", id=message_id, format="full").execute()
        return _extract_gmail_payload_body(message.get("payload", {}))


def _extract_gmail_payload_body(payload: dict[str, Any]) -> str:
    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, dict) and body.get("data"):
        return base64.urlsafe_b64decode(str(body["data"]).encode("ascii")).decode("utf-8", errors="replace")
    parts = payload.get("parts") if isinstance(payload, dict) else None
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("mimeType") == "text/plain":
                part_body = part.get("body")
                if isinstance(part_body, dict) and part_body.get("data"):
                    return base64.urlsafe_b64decode(str(part_body["data"]).encode("ascii")).decode(
                        "utf-8",
                        errors="replace",
                    )
            if str(part.get("mimeType") or "").startswith("multipart/"):
                nested = _extract_gmail_payload_body(part)
                if nested:
                    return nested
    return ""


def _general_gmail_token_path() -> Path | None:
    explicit = os.environ.get("ANIMAWORKS_CI_AUTOFIX_GMAIL_TOKEN")
    if explicit:
        return Path(explicit).expanduser()

    config_path = Path(os.environ.get("ANIMAWORKS_CI_AUTOFIX_GMAIL_CONFIG") or GENERAL_GMAIL_CONFIG_PATH)
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            credentials = data.get("credentials") if isinstance(data, dict) else None
            token = credentials.get("oauth_token") if isinstance(credentials, dict) else None
            if token:
                return Path(str(token)).expanduser()
        except (OSError, json.JSONDecodeError):
            pass

    return GENERAL_GMAIL_TOKEN_PATH if GENERAL_GMAIL_TOKEN_PATH.exists() else None


def default_gmail_client() -> GmailLike:
    token_path = _general_gmail_token_path()
    if token_path and token_path.exists():
        return _ReadonlyGmailClient(token_path)

    from core.tools.gmail import GmailClient

    return GmailClient()


def _is_newer_than_job(message_date: str, job: IntakeJob) -> bool:
    mail_dt = _parse_utc_iso(message_date)
    job_dt = _parse_utc_iso(job.source_date or job.updated_at)
    if mail_dt is None or job_dt is None:
        return False
    return mail_dt > job_dt


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
                    source_date TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '',
                    run_url TEXT NOT NULL DEFAULT '',
                    dry_run INTEGER NOT NULL DEFAULT 1,
                    llm_provider TEXT NOT NULL DEFAULT 'claude_code',
                    llm_model TEXT NOT NULL DEFAULT '',
                    root_run_id TEXT NOT NULL DEFAULT '',
                    last_run_id TEXT NOT NULL DEFAULT '',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    automation_enabled INTEGER NOT NULL DEFAULT 0,
                    next_poll_at TEXT NOT NULL DEFAULT '',
                    last_commit TEXT NOT NULL DEFAULT '',
                    last_conclusion TEXT NOT NULL DEFAULT '',
                    terminal_reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in con.execute("PRAGMA table_info(ci_autofix_jobs)").fetchall()}
            if "llm_provider" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN llm_provider TEXT NOT NULL DEFAULT 'claude_code'")
            if "source_date" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN source_date TEXT NOT NULL DEFAULT ''")
            if "llm_model" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN llm_model TEXT NOT NULL DEFAULT ''")
            if "root_run_id" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN root_run_id TEXT NOT NULL DEFAULT ''")
            if "last_run_id" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN last_run_id TEXT NOT NULL DEFAULT ''")
            if "attempt_count" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            if "max_attempts" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5")
            if "automation_enabled" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN automation_enabled INTEGER NOT NULL DEFAULT 0")
            if "next_poll_at" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN next_poll_at TEXT NOT NULL DEFAULT ''")
            if "last_commit" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN last_commit TEXT NOT NULL DEFAULT ''")
            if "last_conclusion" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN last_conclusion TEXT NOT NULL DEFAULT ''")
            if "terminal_reason" not in columns:
                con.execute("ALTER TABLE ci_autofix_jobs ADD COLUMN terminal_reason TEXT NOT NULL DEFAULT ''")
            con.execute("UPDATE ci_autofix_jobs SET root_run_id = run_id WHERE root_run_id = ''")
            con.execute("UPDATE ci_autofix_jobs SET last_run_id = run_id WHERE last_run_id = ''")
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
        source_date: str = "",
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
                        source_date = COALESCE(NULLIF(?, ''), source_date),
                        subject = COALESCE(NULLIF(?, ''), subject),
                        run_url = COALESCE(NULLIF(?, ''), run_url),
                        llm_provider = COALESCE(NULLIF(?, ''), llm_provider),
                        llm_model = COALESCE(NULLIF(?, ''), llm_model),
                        last_run_id = COALESCE(NULLIF(?, ''), last_run_id),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (source_message_id, source_date, subject, run_url, llm_provider, llm_model, run_id, now, row["id"]),
                )
                updated = con.execute("SELECT * FROM ci_autofix_jobs WHERE id = ?", (row["id"],)).fetchone()
                assert updated is not None
                return self._job_from_row(updated), False

            cur = con.execute(
                """
                INSERT INTO ci_autofix_jobs
                    (run_id, root_run_id, last_run_id, repo, branch, actor, status, source_message_id, source_date, subject, run_url, dry_run, llm_provider, llm_model, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    run_id,
                    run_id,
                    repo,
                    branch,
                    actor,
                    "candidate",
                    source_message_id,
                    source_date,
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

    def list_jobs(self, limit: int = 50, include_terminal: bool = False) -> list[IntakeJob]:
        with self._connect() as con:
            status_filter = "" if include_terminal else f"WHERE status NOT IN ({','.join('?' for _ in TERMINAL_STATUSES)})"
            params: list[Any] = [] if include_terminal else list(TERMINAL_STATUSES)
            params.append(limit)
            rows = con.execute(
                f"""
                SELECT * FROM ci_autofix_jobs
                {status_filter}
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def find_active_job(self, *, repo: str, branch: str, actor: str = "") -> IntakeJob | None:
        params: list[Any] = [repo, branch, *sorted(ACTIVE_STATUSES)]
        actor_filter = ""
        if actor:
            actor_filter = "AND actor = ?"
            params.append(actor)
        with self._connect() as con:
            row = con.execute(
                f"""
                SELECT * FROM ci_autofix_jobs
                WHERE repo = ? AND branch = ?
                  AND status IN ({",".join("?" for _ in sorted(ACTIVE_STATUSES))})
                  {actor_filter}
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return self._job_from_row(row) if row else None

    def link_followup_run(
        self,
        job_id: int,
        *,
        run_id: str,
        run_url: str = "",
        source_message_id: str = "",
        source_date: str = "",
        subject: str = "",
    ) -> IntakeJob:
        now = utc_now()
        with self._connect() as con:
            con.execute(
                """
                UPDATE ci_autofix_jobs
                SET last_run_id = ?,
                    run_url = COALESCE(NULLIF(?, ''), run_url),
                    source_message_id = COALESCE(NULLIF(?, ''), source_message_id),
                    source_date = COALESCE(NULLIF(?, ''), source_date),
                    subject = COALESCE(NULLIF(?, ''), subject),
                    status = CASE WHEN status IN ('completed', 'dismissed', 'failed', 'exhausted') THEN status ELSE 'ci_failed' END,
                    last_conclusion = 'failure',
                    updated_at = ?
                WHERE id = ?
                """,
                (run_id, run_url, source_message_id, source_date, subject, now, job_id),
            )
            row = con.execute("SELECT * FROM ci_autofix_jobs WHERE id = ?", (job_id,)).fetchone()
        assert row is not None
        job = self._job_from_row(row)
        self.add_event(job.id, "warn", "follow-up CI run linked", {"run_id": run_id, "run_url": run_url})
        return job

    def update_job_state(
        self,
        job_id: int,
        *,
        status: str | None = None,
        automation_enabled: bool | None = None,
        max_attempts: int | None = None,
        dry_run: bool | None = None,
        next_poll_at: str | None = None,
        last_run_id: str | None = None,
        run_url: str | None = None,
        last_commit: str | None = None,
        last_conclusion: str | None = None,
        terminal_reason: str | None = None,
    ) -> IntakeJob:
        updates: list[str] = []
        params: list[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if automation_enabled is not None:
            updates.append("automation_enabled = ?")
            params.append(1 if automation_enabled else 0)
        if max_attempts is not None:
            updates.append("max_attempts = ?")
            params.append(max(1, int(max_attempts)))
        if dry_run is not None:
            updates.append("dry_run = ?")
            params.append(1 if dry_run else 0)
        if next_poll_at is not None:
            updates.append("next_poll_at = ?")
            params.append(next_poll_at)
        if last_run_id is not None:
            updates.append("last_run_id = ?")
            params.append(last_run_id)
        if run_url is not None:
            updates.append("run_url = ?")
            params.append(run_url)
        if last_commit is not None:
            updates.append("last_commit = ?")
            params.append(last_commit)
        if last_conclusion is not None:
            updates.append("last_conclusion = ?")
            params.append(last_conclusion)
        if terminal_reason is not None:
            updates.append("terminal_reason = ?")
            params.append(terminal_reason)
        now = utc_now()
        updates.append("updated_at = ?")
        params.extend([now, job_id])
        with self._connect() as con:
            con.execute(f"UPDATE ci_autofix_jobs SET {', '.join(updates)} WHERE id = ?", params)
            row = con.execute("SELECT * FROM ci_autofix_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._job_from_row(row)

    def begin_attempt(self, job_id: int) -> IntakeJob:
        now = utc_now()
        with self._connect() as con:
            con.execute(
                """
                UPDATE ci_autofix_jobs
                SET attempt_count = attempt_count + 1,
                    status = 'running',
                    automation_enabled = 1,
                    next_poll_at = '',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )
            row = con.execute("SELECT * FROM ci_autofix_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        job = self._job_from_row(row)
        self.add_event(
            job.id,
            "info",
            "auto-fix attempt started",
            {"attempt": job.attempt_count, "max_attempts": job.max_attempts, "run_id": job.last_run_id},
        )
        return job

    def summary(self) -> dict[str, Any]:
        jobs = self.list_jobs(limit=100, include_terminal=True)
        active = [job for job in jobs if job.status not in TERMINAL_STATUSES]
        completed = [job for job in jobs if job.status == "completed"]
        dismissed = [job for job in jobs if job.status == "dismissed"]
        exhausted = [job for job in jobs if job.status == "exhausted"]
        latest = active[0] if active else (jobs[0] if jobs else None)
        return {
            "active_count": len(active),
            "total_count": len(jobs),
            "completed_count": len(completed),
            "dismissed_count": len(dismissed),
            "exhausted_count": len(exhausted),
            "terminal_count": len(jobs) - len(active),
            "latest": latest.to_dict() if latest else None,
            "latest_completed": completed[0].to_dict() if completed else None,
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
            root_run_id=str(row["root_run_id"] or row["run_id"]),
            last_run_id=str(row["last_run_id"] or row["run_id"]),
            repo=str(row["repo"]),
            branch=str(row["branch"]),
            actor=str(row["actor"]),
            status=str(row["status"]),
            source_message_id=str(row["source_message_id"]),
            source_date=str(row["source_date"]),
            subject=str(row["subject"]),
            run_url=str(row["run_url"]),
            dry_run=bool(row["dry_run"]),
            llm_provider=str(row["llm_provider"]),
            llm_model=str(row["llm_model"]),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            automation_enabled=bool(row["automation_enabled"]),
            next_poll_at=str(row["next_poll_at"]),
            last_commit=str(row["last_commit"]),
            last_conclusion=str(row["last_conclusion"]),
            terminal_reason=str(row["terminal_reason"]),
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
        gmail_client = default_gmail_client()

    query = rule.resolved_query()
    messages = list(gmail_client.search_emails(query=query, max_results=rule.max_results))
    created: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    linked: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []

    for message in messages:
        message_id = str(getattr(message, "id", "") or "")
        subject = str(getattr(message, "subject", "") or "")
        snippet = str(getattr(message, "snippet", "") or "")
        message_date = parse_mail_date(str(getattr(message, "date", "") or ""))
        body = gmail_client.get_email_body(message_id) if message_id else ""
        text = "\n".join([subject, snippet, body])
        run_ids = extract_actions_run_ids(text)
        if not run_ids:
            continue
        run_id = run_ids[0]
        run_url = f"https://github.com/{rule.repo}/actions/runs/{run_id}"
        active_job = store.find_active_job(repo=rule.repo, branch=rule.branch, actor=rule.actor)
        if active_job and run_id not in {active_job.run_id, active_job.last_run_id}:
            if not _is_newer_than_job(message_date, active_job):
                store.add_event(
                    active_job.id,
                    "info",
                    "stale Gmail failure ignored",
                    {
                        "message_id": message_id,
                        "message_date": message_date,
                        "subject": subject,
                        "run_id": run_id,
                        "active_source_date": active_job.source_date,
                        "active_updated_at": active_job.updated_at,
                    },
                )
                stale.append(
                    {
                        "run_id": run_id,
                        "message_id": message_id,
                        "message_date": message_date,
                        "subject": subject,
                        "active_job_id": active_job.id,
                    }
                )
                continue
            job = store.link_followup_run(
                active_job.id,
                run_id=run_id,
                run_url=run_url,
                source_message_id=message_id,
                source_date=message_date,
                subject=subject,
            )
            was_created = False
            was_linked = True
        else:
            job, was_created = store.upsert_candidate(
                run_id=run_id,
                repo=rule.repo,
                branch=rule.branch,
                actor=rule.actor,
                source_message_id=message_id,
                source_date=message_date,
                subject=subject,
                run_url=run_url,
                dry_run=rule.dry_run,
                llm_provider=rule.llm_provider,
                llm_model=rule.llm_model,
            )
            was_linked = False
        store.add_event(
            job.id,
            "info",
            "gmail message matched",
            {
                "message_id": message_id,
                "message_date": message_date,
                "subject": subject,
                "query": query,
                "ignored_run_ids": run_ids[1:],
            },
        )
        if was_created:
            created.append(job.to_dict())
        elif was_linked:
            linked.append(job.to_dict())
        else:
            existing.append(job.to_dict())

    return {
        "ok": True,
        "query": query,
        "checked": len(messages),
        "created": created,
        "linked": linked,
        "existing": existing,
        "stale": stale,
    }
