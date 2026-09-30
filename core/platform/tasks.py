from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Helpers for safely spawning detached asyncio tasks."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
    """Create a detached task, keep it alive, and report any unhandled failure."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)

    def _on_done(done: asyncio.Task[Any]) -> None:
        _background_tasks.discard(done)
        if done.cancelled():
            return
        exception = done.exception()
        if exception is not None:
            logger.error(
                "Background task %s failed",
                done.get_name(),
                exc_info=(type(exception), exception, exception.__traceback__),
            )

    task.add_done_callback(_on_done)
    return task
