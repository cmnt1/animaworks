from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Batched task board notices.

Each ``task cancel/done/note`` is its own CLI process, so a triage pass that
closes forty tasks used to send forty DMs and tripped the conversation depth
limit after six. Notices are queued per (actor, recipient) instead, and the
supervisor sends one digest per pair once the actor has been quiet for a while.
"""

import fcntl
import hashlib
import json
import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

QUIET_SECONDS = 120.0
_MAX_LINES = 30
_DETAIL_CHARS = 140


def _queue_dir() -> Path:
    from core.paths import get_shared_dir

    return get_shared_dir() / "task_notices"


@contextmanager
def _locked(queue_dir: Path):
    queue_dir.mkdir(parents=True, exist_ok=True)
    with (queue_dir / ".lock").open("a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def queue_task_notice(
    actor: str, to: str, task_id: str, action: str, detail: str, *, owner: str | None = None
) -> str | None:
    """Queue one notice for the next digest. Returns a warning on failure."""
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "actor": actor,
        "to": to,
        "target": f"{owner}/{task_id}" if owner else task_id,
        "action": action,
        "detail": detail,
    }
    try:
        queue_dir = _queue_dir()
        with _locked(queue_dir), (queue_dir / f"{actor}__{to}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        # Task state is authoritative; notification delivery must not roll it back.
        return f"task changed, but notification to {to} could not be queued: {exc}"
    return None


def format_digest(actor: str, records: list[dict[str, Any]]) -> str:
    lines = [f"{actor} changed {len(records)} task(s) on the board:"]
    for rec in records[:_MAX_LINES]:
        detail = " ".join(str(rec.get("detail", "")).split())[:_DETAIL_CHARS]
        lines.append(f"- {rec['action']} {rec['target']}: {detail}")
    if len(records) > _MAX_LINES:
        lines.append(f"- ... {len(records) - _MAX_LINES} more (animaworks-tool task show ID)")
    return "\n".join(lines)


def _send_digest(actor: str, to: str, records: list[dict[str, Any]]) -> bool:
    from cli.commands.messaging import _resolve_sender_source
    from core.messenger import Messenger
    from core.paths import get_shared_dir

    content = format_digest(actor, records)
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:20]
    message = Messenger(get_shared_dir(), actor).send(
        to=to,
        content=content,
        source=_resolve_sender_source(actor),
        delivery_id=f"tasknotice-{digest}",
    )
    if message.type == "error":
        logger.warning("Task notice digest %s -> %s not sent: %s", actor, to, message.content)
        return False
    return True


def flush_task_notices(quiet_seconds: float = QUIET_SECONDS) -> int:
    """Send one digest per queued pair whose actor has gone quiet. Returns digests sent."""
    queue_dir = _queue_dir()
    if not queue_dir.is_dir():
        return 0
    sent = 0
    now = time.time()
    with _locked(queue_dir):
        for path in sorted(queue_dir.glob("*__*.jsonl")):
            try:
                if now - path.stat().st_mtime < quiet_seconds:
                    continue
                records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if not records:
                    path.unlink(missing_ok=True)
                    continue
                actor, to = records[0]["actor"], records[0]["to"]
                if _send_digest(actor, to, records):
                    path.unlink(missing_ok=True)
                    sent += 1
            except Exception:
                # Leave the file for the next tick; a failed digest is retried, not dropped.
                logger.exception("Failed to flush task notices from %s", path.name)
    return sent
