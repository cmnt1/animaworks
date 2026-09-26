from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Graceful interrupt helpers for Agent SDK streaming and blocking modes.

Sends ``client.interrupt()`` to the CLI subprocess and saves the
``session_id`` so the session can be resumed later.  Both functions
are bounded by ``INTERRUPT_TIMEOUT_SEC`` to prevent hangs.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    try:
        from claude_agent_sdk import ClaudeSDKClient
    except ImportError:
        pass

from core.execution.engines.claude._sdk_session import (
    _RESUMABLE_SESSION_TYPES,
    INTERRUPT_TIMEOUT_SEC,
    _save_session_id,
)

logger = logging.getLogger("animaworks.execution.agent_sdk")


async def _graceful_interrupt_stream(
    client: ClaudeSDKClient,
    anima_dir: Path,
    session_type: str,
    captured_session_id: str | None,
    *,
    thread_id: str = "default",
) -> None:
    """Send graceful interrupt to CLI and save session_id.

    Primary path: ``client.interrupt()`` → wait for ``ResultMessage`` →
    save ``session_id``.  Fallback: use the ``session_id`` captured from
    the most recent ``StreamEvent`` if interrupt times out.

    The entire interrupt + receive sequence is bounded by
    ``INTERRUPT_TIMEOUT_SEC`` to prevent hangs when the CLI does not
    respond after acknowledging the interrupt.
    """
    from claude_agent_sdk import ResultMessage

    async def _interrupt_and_receive() -> str | None:
        await client.interrupt()
        async for msg in client.receive_messages():
            if isinstance(msg, ResultMessage):
                return msg.session_id
        return None

    try:
        sid = await asyncio.wait_for(_interrupt_and_receive(), timeout=INTERRUPT_TIMEOUT_SEC)
        if sid and session_type in _RESUMABLE_SESSION_TYPES:
            _save_session_id(anima_dir, sid, session_type, thread_id=thread_id)
            logger.info("Saved session_id from ResultMessage after interrupt")
    except Exception:
        if captured_session_id and session_type in _RESUMABLE_SESSION_TYPES:
            _save_session_id(anima_dir, captured_session_id, session_type, thread_id=thread_id)
            logger.warning("interrupt() failed; saved session_id from StreamEvent fallback")
        else:
            logger.warning("interrupt() failed and no StreamEvent session_id available")


async def _graceful_interrupt_blocking(
    client: ClaudeSDKClient,
    anima_dir: Path,
    session_type: str,
    *,
    thread_id: str = "default",
) -> None:
    """Send graceful interrupt to CLI in blocking mode and save session_id.

    ``receive_response()`` does not yield ``StreamEvent``, so there is no
    fallback — only the ``ResultMessage`` path.  The entire sequence is
    bounded by ``INTERRUPT_TIMEOUT_SEC``.
    """
    from claude_agent_sdk import ResultMessage

    async def _interrupt_and_receive() -> str | None:
        await client.interrupt()
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                return msg.session_id
        return None

    try:
        sid = await asyncio.wait_for(_interrupt_and_receive(), timeout=INTERRUPT_TIMEOUT_SEC)
        if sid and session_type in _RESUMABLE_SESSION_TYPES:
            _save_session_id(anima_dir, sid, session_type, thread_id=thread_id)
            logger.info("Saved session_id from ResultMessage after blocking interrupt")
    except Exception:
        logger.warning("interrupt() failed in blocking mode; session_id not saved")
