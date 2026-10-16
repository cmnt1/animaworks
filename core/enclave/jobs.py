# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Persistent query jobs for the enclave gateway.

Each ``POST /v1/ask`` becomes an :class:`EnclaveJob` stored under
``{data_dir}/state/enclave_jobs/{job_id}.json``.  Jobs survive a gateway
restart so callers can still read status and results; queued/running jobs
left behind by a restart are marked ``failed`` with ``enclave_restarted``.
Per-job progress lines are appended to ``{job_id}.progress.jsonl``.

All writes are atomic (tmp + rename) through :mod:`core.platform.atomic_io`,
and the job directory is created with mode 0700 because job bodies and facts
are private to the enclave.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from core.enclave.egress.fs import ensure_dir_0700
from core.platform.atomic_io import atomic_write_json, atomic_write_text

logger = logging.getLogger(__name__)

# Terminal plus transient states.  ``queued``/``running`` are transient.
_FINISHED = ("done", "failed", "cancelled")

_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,36}$")


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def make_thread_id(case_id: str) -> str:
    """Map a case_id onto the thread_id rules (1-36 chars of ``[A-Za-z0-9_-]``).

    ``enclave-{case_id}`` is used verbatim when it already satisfies the
    rules.  Otherwise non-permitted characters are replaced with ``-``, the
    front is truncated, and a ``sha1(case_id)`` prefix is appended so every
    case_id maps to a stable, unique thread_id within 36 characters.
    """
    candidate = f"enclave-{case_id}"
    if _THREAD_ID_RE.fullmatch(candidate):
        return candidate

    sanitized = re.sub(r"[^A-Za-z0-9_-]", "-", case_id)
    digest = hashlib_sha1(case_id)
    suffix = f"-{digest}"
    max_prefix = 36 - len(suffix)
    prefix = sanitized
    if len(prefix) > max_prefix:
        prefix = prefix[-max_prefix:]
    thread_id = f"{prefix}{suffix}"
    if not _THREAD_ID_RE.fullmatch(thread_id):
        # Last-resort fallback: always a valid thread id for this case_id.
        thread_id = f"c-{digest}"[:36]
    return thread_id


def hashlib_sha1(value: str) -> str:
    """Return the first 8 hex chars of the sha1 of *value*."""
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


@dataclass
class EnclaveJob:
    """A single enclave ask job (mutable; persisted to disk)."""

    job_id: str
    case_id: str
    from_anima: str
    question: str
    thread_id: str
    status: str = "queued"
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    last_activity_at: str = ""
    facts: list = field(default_factory=list)
    error: str = ""
    audit_id: str = ""
    delivered: bool = False
    model_profile: str = ""


class EnclaveJobStore:
    """Persistent store for :class:`EnclaveJob` under ``data_dir/state``."""

    _RETENTION_DAYS = 30

    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir) / "state" / "enclave_jobs"
        self._cache: dict[str, EnclaveJob] = {}

    # -- paths ---------------------------------------------------------

    def _job_path(self, job_id: str) -> Path:
        return self._dir / f"{job_id}.json"

    def _progress_path(self, job_id: str) -> Path:
        return self._dir / f"{job_id}.progress.jsonl"

    # -- persistence ---------------------------------------------------

    def save(self, job: EnclaveJob) -> None:
        """Write *job* to disk atomically and update the in-memory cache."""
        ensure_dir_0700(self._dir)
        atomic_write_json(
            self._job_path(job.job_id),
            {
                "job_id": job.job_id,
                "case_id": job.case_id,
                "from_anima": job.from_anima,
                "question": job.question,
                "thread_id": job.thread_id,
                "status": job.status,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "last_activity_at": job.last_activity_at,
                "facts": job.facts,
                "error": job.error,
                "audit_id": job.audit_id,
                "delivered": job.delivered,
                "model_profile": job.model_profile,
            },
            mode=0o600,
            ensure_ascii=False,
        )
        self._cache[job.job_id] = job

    def load(self, job_id: str) -> EnclaveJob | None:
        """Return the job with *job_id* or ``None`` when absent."""
        cached = self._cache.get(job_id)
        if cached is not None:
            return cached
        path = self._job_path(job_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            job = EnclaveJob(**data)
        except (OSError, ValueError, TypeError):
            logger.warning("enclave jobs: could not load job %s", job_id, exc_info=True)
            return None
        self._cache[job_id] = job
        return job

    def list_all(self) -> list[EnclaveJob]:
        """Return every job known on disk plus any in-memory ones."""
        jobs: dict[str, EnclaveJob] = {}
        if self._dir.exists():
            for path in self._dir.glob("*.json"):
                try:
                    job = EnclaveJob(**json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError, TypeError):
                    continue
                jobs[job.job_id] = job
        for job_id, job in self._cache.items():
            jobs.setdefault(job_id, job)
        return list(jobs.values())

    def find_active(self, from_anima: str, case_id: str) -> EnclaveJob | None:
        """Return the first queued/running job for ``(from_anima, case_id)``."""
        for job in self.list_all():
            if job.from_anima == from_anima and job.case_id == case_id and job.status in ("queued", "running"):
                return job
        return None

    # -- lifecycle ----------------------------------------------------

    def restart_mark_failed(self) -> None:
        """Mark any left-over queued/running jobs as failed after a restart."""
        for job in self.list_all():
            if job.status in ("queued", "running"):
                job.status = "failed"
                job.error = "enclave_restarted"
                job.finished_at = utcnow_iso()
                self.save(job)

    def cleanup(self) -> None:
        """Delete delivered jobs finished more than ``_RETENTION_DAYS`` ago."""
        cutoff = time.time() - self._RETENTION_DAYS * 86_400
        for job in self.list_all():
            if not (job.delivered and job.finished_at):
                continue
            try:
                finished_ts = datetime.fromisoformat(job.finished_at).timestamp()
            except (ValueError, TypeError):
                continue
            if finished_ts < cutoff:
                try:
                    self._job_path(job.job_id).unlink()
                except OSError:
                    logger.warning("enclave jobs: could not remove stale job %s", job.job_id, exc_info=True)
                self._cache.pop(job.job_id, None)

    # -- progress -----------------------------------------------------

    def write_progress(self, job_id: str, text: str) -> tuple[bool, str]:
        """Append one progress line for a running job.

        Returns ``(True, "")`` on success, or ``(False, reason)`` where
        reason is ``"not_found"`` / ``"not_running"``.
        """
        job = self.load(job_id)
        if job is None:
            return False, "not_found"
        if job.status != "running":
            return False, "not_running"
        entries = self.read_progress(job_id)
        entries.append({"at": utcnow_iso(), "text": text})
        ensure_dir_0700(self._dir)
        content = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
        # Only the progress file is written here: this runs in the anima's tool
        # process, and saving the job JSON would race with the gateway's writes.
        atomic_write_text(self._progress_path(job_id), content, mode=0o600)
        return True, ""

    def read_progress(self, job_id: str) -> list[dict]:
        """Return the raw progress entries for *job_id* (unmasked)."""
        path = self._progress_path(job_id)
        if not path.exists():
            return []
        entries: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries


__all__ = [
    "EnclaveJob",
    "EnclaveJobStore",
    "make_thread_id",
    "utcnow_iso",
]
