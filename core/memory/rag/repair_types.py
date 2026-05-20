from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Types for RAG auto-repair."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairResult:
    """Result returned by a synchronous repair attempt."""

    status: str
    anima_name: str
    reason: str
    quarantine_path: str | None = None
    chunks_indexed: int = 0
    error: str | None = None
    stage: str | None = None
    state_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "success"
