from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Format priming result as Markdown section for system prompt injection."""

from core.i18n import t
from core.memory.priming.result import PrimingResult


def _wrap(result: PrimingResult, channel: str, source: str, content: str, *, trust: str = "mixed", **kwargs) -> str:
    """Wrap one channel's content verbatim in a ``<priming>`` boundary."""
    # Imported lazily to avoid a circular import during module load.
    from core.execution._sanitize import wrap_priming

    if not content:
        return ""
    return wrap_priming(source, content, trust=trust, **kwargs)


def format_priming_section(result: PrimingResult, sender_name: str = "human") -> str:
    """Format priming result as a Markdown section for system prompt injection.

    Each non-empty channel is wrapped in ``<priming source=... trust=...>``
    unchanged; resident pointer lines are passed through as-is (they are
    already one-line score/path/summary cues).

    Args:
        result: The priming result to format
        sender_name: Name of the message sender

    Returns:
        Formatted markdown section, or empty string if no memories primed
    """
    # Imported lazily to avoid a circular import during module load.
    from core.execution._sanitize import ORIGIN_CONSOLIDATION, ORIGIN_MIXED, wrap_priming

    if result.is_empty():
        return ""

    parts: list[str] = []
    parts.append(t("priming.section_title"))
    parts.append("")
    parts.append(t("priming.section_intro"))
    parts.append("")

    if result.sender_profile:
        parts.append(t("priming.about_sender", sender_name=sender_name))
        parts.append("")
        parts.append(_wrap(result, "sender_profile", "sender_profile", result.sender_profile, trust="medium"))
        parts.append("")

    if result.resident_knowledge:
        parts.append(wrap_priming("resident_knowledge", result.resident_knowledge, trust="medium"))
        parts.append("")

    if result.recent_activity:
        parts.append(t("priming.recent_activity_header"))
        parts.append("")
        parts.append(_wrap(result, "recent_activity", "recent_activity", result.recent_activity, trust="untrusted"))
        parts.append("")

    if result.related_knowledge or result.related_knowledge_untrusted:
        parts.append(t("priming.related_knowledge_header"))
        parts.append("")
        if result.related_knowledge:
            medium_kwargs = {"origin": ORIGIN_CONSOLIDATION} if result.related_knowledge_untrusted else {}
            parts.append(
                _wrap(
                    result,
                    "related_knowledge",
                    "related_knowledge",
                    result.related_knowledge,
                    trust="medium",
                    **medium_kwargs,
                )
            )
            parts.append("")
        if result.related_knowledge_untrusted:
            parts.append(
                _wrap(
                    result,
                    "related_knowledge_untrusted",
                    "related_knowledge_external",
                    result.related_knowledge_untrusted,
                    trust="untrusted",
                    origin=ORIGIN_MIXED,
                )
            )
            parts.append("")

    if result.episodes:
        parts.append(t("priming.episodes_header"))
        parts.append("")
        parts.append(_wrap(result, "episodes", "episodes", result.episodes, trust="medium"))
        parts.append("")

    if result.pending_tasks:
        parts.append(t("priming.pending_tasks_header"))
        parts.append("")
        parts.append(_wrap(result, "pending_tasks", "pending_tasks", result.pending_tasks, trust="medium"))
        parts.append("")

    if result.recent_outbound:
        parts.append(_wrap(result, "recent_outbound", "recent_outbound", result.recent_outbound, trust="trusted"))
        parts.append("")

    if result.graph_context:
        parts.append(_wrap(result, "graph_context", "graph_context", result.graph_context, trust="medium"))
        parts.append("")

    return "\n".join(parts)
