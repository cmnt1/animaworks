from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Prompt-log constants and helpers extracted from ``core.agent.agent_core``.

Pure entry construction lives here; state persistence is delegated to the
process-scoped ``StateWriter``.
"""

import logging
from datetime import timedelta
from pathlib import Path

from core.execution.session.session_context import current_runtime_session
from core.platform.state_writer import get_state_writer, run_writer_sync
from core.time_utils import now_iso, now_local

logger = logging.getLogger("animaworks.agent")

# ── Prompt size guards ──────────────────────────────────────────
_PROMPT_SOFT_LIMIT_BYTES = 600_000
_PROMPT_HARD_LIMIT_BYTES = 1_200_000
_PROMPT_LOG_RETENTION_DAYS = 3
_last_rotation_date: str | None = None


def _rotate_prompt_logs(log_dir: Path) -> None:
    """Synchronously rotate one Anima's prompt logs through StateWriter."""
    global _last_rotation_date
    writer = get_state_writer(log_dir.parent)
    run_writer_sync(writer, writer.rotate_prompt_logs())
    _last_rotation_date = now_local().strftime("%Y-%m-%d")


async def _save_prompt_log(
    anima_dir: Path,
    *,
    trigger: str,
    sender: str,
    model: str,
    mode: str,
    system_prompt: str,
    user_message: str,
    tools: list[str],
    session_id: str,
    context_window: int = 0,
    prior_messages: list | None = None,
    tool_schemas: list | None = None,
    request_id: str = "",
    session_type: str = "",
    thread_id: str = "",
    tool_session_id: str = "",
    sdk_session_id: str = "",
) -> None:
    """Persist one request-start record without blocking the task-runner loop."""
    try:
        today = now_iso()[:10]
        ctx = current_runtime_session()
        entry = {
            "ts": now_iso(),
            "type": "request_start",
            "request_id": request_id or (ctx.request_id if ctx else ""),
            "trigger": trigger,
            "session_type": session_type or (ctx.session_type if ctx else ""),
            "thread_id": thread_id or (ctx.thread_id if ctx else ""),
            "from": sender,
            "model": model,
            "mode": mode,
            "system_prompt_length": len(system_prompt),
            "system_prompt": system_prompt,
            "user_message": user_message,
            "tools": tools,
            "session_id": session_id,
            "tool_session_id": tool_session_id or (ctx.tool_session_id if ctx else session_id),
            "sdk_session_id": sdk_session_id,
            "context_window": context_window,
            "prior_messages": prior_messages,
            "prior_messages_count": len(prior_messages) if prior_messages else 0,
            "tool_schemas": tool_schemas,
        }
        await get_state_writer(anima_dir).log_prompt(entry)
        logger.debug("Prompt log saved for %s (%d bytes)", today, len(system_prompt))
    except Exception:
        logger.warning("Failed to save prompt log", exc_info=True)


async def _save_prompt_log_end(
    anima_dir: Path,
    session_id: str,
    final_messages: list[dict] | None = None,
    tool_call_count: int = 0,
    total_tokens_estimate: int = 0,
    request_id: str = "",
    session_type: str = "",
    thread_id: str = "",
    trigger: str = "",
    tool_session_id: str = "",
    sdk_session_id: str = "",
) -> None:
    """Persist post-execution metadata to the prompt log."""
    try:
        ctx = current_runtime_session()
        entry = {
            "ts": now_iso(),
            "type": "request_end",
            "request_id": request_id or (ctx.request_id if ctx else ""),
            "session_id": session_id,
            "session_type": session_type or (ctx.session_type if ctx else ""),
            "thread_id": thread_id or (ctx.thread_id if ctx else ""),
            "trigger": trigger or (ctx.trigger if ctx else ""),
            "tool_session_id": tool_session_id or (ctx.tool_session_id if ctx else session_id),
            "sdk_session_id": sdk_session_id,
            "final_messages_count": len(final_messages) if final_messages else 0,
            "final_messages": final_messages,
            "tool_call_count": tool_call_count,
            "total_tokens_estimate": total_tokens_estimate,
        }
        await get_state_writer(anima_dir).log_prompt_end(entry)
    except Exception:
        logger.warning("Failed to save prompt log end", exc_info=True)


def rotate_all_prompt_logs(
    animas_dir: Path,
    retention_days: int = 3,
) -> dict[str, int]:
    """Rotate prompt logs for all Animas under *animas_dir*.

    This server-side maintenance helper is not used by task-runner prompt writes.
    Returns the number of deleted files per Anima.
    """
    cutoff = now_local() - timedelta(days=retention_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    results: dict[str, int] = {}
    for anima_dir in sorted(animas_dir.iterdir()):
        if not anima_dir.is_dir():
            continue
        log_dir = anima_dir / "prompt_logs"
        if not log_dir.is_dir():
            continue
        deleted = 0
        for path in log_dir.glob("*.jsonl"):
            if path.stem < cutoff_str:
                path.unlink(missing_ok=True)
                deleted += 1
        if deleted:
            results[anima_dir.name] = deleted
    return results
