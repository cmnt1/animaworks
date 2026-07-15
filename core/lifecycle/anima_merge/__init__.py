from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Resumable Anima merge lifecycle (Phase 1)."""

from .journal import MergeJournal, MergePhase
from .service import AnimaMergeError, AnimaMergeService, MergeResult

__all__ = [
    "AnimaMergeError",
    "AnimaMergeService",
    "MergeJournal",
    "MergePhase",
    "MergeResult",
]
