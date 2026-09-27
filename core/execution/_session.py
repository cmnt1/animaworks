from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Shared session helpers for execution engines.

LiteLLMExecutor monitors context usage and saves short-term memory when the
configured threshold is crossed. The next incoming message picks up the saved
state via ``inject_shortterm``; no in-flight session chaining is performed.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.conversation.shortterm import StreamCheckpoint

from core.i18n import t
from core.memory.conversation.shortterm import SessionState, ShortTermMemory
from core.prompt.context import ContextTracker
from core.time_utils import now_iso

logger = logging.getLogger("animaworks.execution.session")


def save_threshold_shortterm(
    tracker: ContextTracker,
    shortterm: ShortTermMemory | None,
    *,
    session_id: str,
    trigger: str,
    original_prompt: str,
    accumulated_response: str,
    current_text: str,
    turn_count: int,
    tool_uses: list[dict],
) -> bool:
    """Save session state when context threshold is exceeded and storage exists."""
    if shortterm is None or not tracker.threshold_exceeded:
        return False

    logger.info(
        "Session context at %.1f%% — saving shortterm, will resume on next message",
        tracker.usage_ratio * 100,
    )
    full_accumulated = accumulated_response
    if current_text:
        full_accumulated = f"{accumulated_response}\n{current_text}" if accumulated_response else current_text

    shortterm.save(
        SessionState(
            session_id=session_id,
            timestamp=now_iso(),
            trigger=trigger,
            original_prompt=original_prompt,
            accumulated_response=full_accumulated,
            tool_uses=tool_uses,
            context_usage_ratio=tracker.usage_ratio,
            turn_count=turn_count,
        )
    )
    return True


def build_stream_retry_prompt(checkpoint: StreamCheckpoint) -> str:
    """Build a continuation prompt from a stream checkpoint.

    Summarises what was completed before the disconnect and instructs the
    LLM to continue from where it left off.

    Args:
        checkpoint: The checkpoint recorded during the interrupted stream.

    Returns:
        A prompt string for the retry session.
    """

    completed_lines: list[str] = []
    for i, tool in enumerate(checkpoint.completed_tools, 1):
        name = tool.get("tool_name", "unknown")
        summary = tool.get("summary", "")
        completed_lines.append(f"{i}. ✅ {name}: {summary}")

    completed_section = "\n".join(completed_lines) if completed_lines else t("session.completed_none")

    # Truncate accumulated text to avoid oversized prompt
    acc_text = checkpoint.accumulated_text
    if len(acc_text) > 2000:
        acc_text = t("session.text_truncated") + "\n" + acc_text[-2000:]

    return (
        t("session.continuation_intro") + "\n"
        "\n"
        f"{t('session.original_instruction_header')}\n"
        f"{checkpoint.original_prompt}\n"
        "\n"
        f"{t('session.completed_steps_header')}\n"
        f"{completed_section}\n"
        "\n"
        f"{t('session.output_so_far_header')}\n"
        f"{acc_text}\n"
        "\n"
        f"{t('session.caution_header')}\n"
        f"- {t('session.caution_no_repeat')}\n"
        f"- {t('session.caution_skip_existing')}\n"
        f"- {t('session.caution_continue')}\n"
    )
