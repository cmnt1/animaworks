from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Messaging, human notification, and recent tool section building."""

import logging
from pathlib import Path
from typing import Any

from core.paths import PROJECT_DIR, load_prompt
from core.prompt.org_context import _is_mcp_mode
from core.prompt.sections import _load_fallback_strings, _load_section_strings

logger = logging.getLogger("animaworks.prompt_builder")


def _build_messaging_section(
    anima_dir: Path,
    other_animas: list[str],
    execution_mode: str = "s",
) -> str:
    """Build the messaging instructions with resolved paths."""
    from core.tooling.prompt_db import get_prompt_store

    _fs = _load_fallback_strings()
    self_name = anima_dir.name
    main_py = PROJECT_DIR / "main.py"
    animas_line = ", ".join(other_animas) if other_animas else _fs.get("no_other_animas", "(no other employees yet)")

    db_key = "messaging_s" if _is_mcp_mode(execution_mode) else "messaging"
    _msg_store = get_prompt_store()
    raw = _msg_store.get_section(db_key) if _msg_store else None
    if raw:
        try:
            return raw.format(
                animas_line=animas_line,
                main_py=main_py,
                self_name=self_name,
            )
        except (KeyError, IndexError):
            return raw
    return load_prompt(
        db_key,
        animas_line=animas_line,
        main_py=main_py,
        self_name=self_name,
    )


def _load_a_reflection() -> str:
    """Load the A mode reflection/retry prompt template."""
    try:
        return load_prompt("a_reflection")
    except Exception:
        logger.debug("a_reflection template not found, skipping")
        return ""


def _build_recent_tool_section(anima_dir: Path, model_config: Any) -> str:
    """Build a summary of recent tool results for system prompt injection.

    Reads the last few turns from ConversationMemory and extracts tool
    records with result summaries, constrained to a ~2000 token budget.
    """
    try:
        from core.memory.conversation import ConversationMemory

        conv_memory = ConversationMemory(anima_dir, model_config)
        state = conv_memory.load()
    except Exception:
        return ""
    if not state.turns:
        return ""

    tool_lines: list[str] = []
    budget_remaining = 2000  # approximate token budget (~8000 chars)
    for turn in reversed(state.turns[-3:]):
        for tr in turn.tool_records[:5]:
            if not tr.result_summary:
                continue
            line = f"- {tr.tool_name}: {tr.result_summary[:500]}"
            budget_remaining -= len(line) // 4
            if budget_remaining <= 0:
                break
            tool_lines.append(line)
        if budget_remaining <= 0:
            break

    if not tool_lines:
        return ""
    _ss = _load_section_strings()
    header = _ss.get("recent_tool_results_header", "## Recent Tool Results")
    return f"{header}\n\n" + "\n".join(tool_lines)


def _build_human_notification_guidance(execution_mode: str = "") -> str:
    """Build the human notification instruction for top-level Animas."""
    if _is_mcp_mode(execution_mode):
        how_to = load_prompt("builder/human_notification_howto_s")
    else:
        how_to = load_prompt("builder/human_notification_howto_other")

    return load_prompt("builder/human_notification", how_to=how_to)
