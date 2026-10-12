# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Priming layer - automatic memory retrieval (自動想起).

Implements brain-science-inspired automatic memory activation before agent
execution, reducing the need for explicit search_memory tool calls.

Based on: docs/design/priming-layer-design.md Phase 1

Active channels: A (sender profile), B (recent activity), C (related knowledge),
E (pending tasks), F (episodes), and G (recent atomic facts).
"""

from __future__ import annotations

# Load submodules first so engine can import them without circular import
from core.memory.priming import (
    channel_a,
    channel_b,
    channel_c,
    channel_e,
    channel_f,
    channel_g,
    outbound,
)
from core.memory.priming.constants import (
    _BUDGET_IMPORTANT_KNOWLEDGE,
    _DEFAULT_MAX_PRIMING_TOKENS,
    _MAX_KEYWORD_INPUT_LEN,
    _MINIMAL_STOPWORDS,
    _RE_UNICODE_WORDS,
)
from core.memory.priming.engine import PrimingEngine, PrimingResult
from core.memory.priming.format import format_priming_section
from core.memory.priming.items import MemoryItem, render_items, select_within_budget

__all__ = [
    "PrimingEngine",
    "PrimingResult",
    "MemoryItem",
    "format_priming_section",
    "render_items",
    "select_within_budget",
    "_BUDGET_IMPORTANT_KNOWLEDGE",
    "_DEFAULT_MAX_PRIMING_TOKENS",
    "_MAX_KEYWORD_INPUT_LEN",
    "_MINIMAL_STOPWORDS",
    "_RE_UNICODE_WORDS",
]
