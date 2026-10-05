from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Runtime facade for the platform-level StateWriter implementations."""

from core.platform.state_writer import (
    IpcStateWriter,
    LocalStateWriter,
    StateWriterError,
    configure_state_writer,
    get_state_writer,
    is_task_runner_process,
    run_writer_sync,
)

__all__ = [
    "IpcStateWriter",
    "LocalStateWriter",
    "StateWriterError",
    "configure_state_writer",
    "get_state_writer",
    "is_task_runner_process",
    "run_writer_sync",
]
