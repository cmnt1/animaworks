from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Model-based task granularity guardrails.

The policy here is intentionally model-based, not Anima-based.  Anima model
assignments move over time, so task breadth should follow the model actually
used for background execution.
"""

import fnmatch
import re
from dataclasses import dataclass

from core.config.model_mode import resolve_tool_use_capability


@dataclass(frozen=True)
class TaskGranularityDecision:
    allowed: bool
    model_name: str
    capability: str
    phase_count: int
    limit: int
    reason: str = ""
    guidance: str = ""


_MEDIUM_MODEL_HINTS = (
    "*qwen3-coder*",
    "*qwen3*30b*",
    "*qwen3*32b*",
    "*qwen3*14b*",
    "*glm*",
    "*devstral*",
)

_PHASE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("inspect", ("inspect", "investigate", "check", "audit", "confirm", "verify current", "look up", "調査", "確認", "検証")),
    ("db_fix", ("db", "database", "sql", "record", "migration", "repair", "fix", "修正", "補正", "復旧")),
    ("sync", ("sync", "synchronize", "export", "import", "同期")),
    ("build", ("build", "compile", "generate", "生成")),
    ("deploy", ("deploy", "release", "publish", "公開", "反映")),
    ("verify", ("verify", "public", "url", "http", "200", "screenshot", "confirm", "公開確認", "疎通")),
    ("report", ("report", "notify", "escalate", "handoff", "報告", "証跡", "提出")),
)

_BOUNDARY_RE = re.compile(r"(?:->|=>|→|⇒|/|／|,|、|;|；|\+|＋|・|\n|\bthen\b|\band then\b|と)", re.IGNORECASE)


def capability_for_model(model_name: str) -> str:
    normalized = (model_name or "").strip()
    if not normalized:
        return "high"
    lowered = normalized.casefold()
    for pattern in _MEDIUM_MODEL_HINTS:
        if fnmatch.fnmatch(lowered, pattern):
            return "medium"
    return resolve_tool_use_capability(normalized)


_capability_for_model = capability_for_model


def _phase_limit(capability: str) -> int:
    if capability == "high":
        return 999
    if capability == "medium":
        return 2
    return 1


def estimate_phase_count(text: str) -> int:
    """Return a conservative phase count for operational task breadth."""
    folded = (text or "").casefold()
    if not folded.strip():
        return 0

    matched = 0
    for _name, markers in _PHASE_PATTERNS:
        if any(marker in folded for marker in markers):
            matched += 1

    boundary_count = len([part for part in _BOUNDARY_RE.split(folded) if part.strip()])
    if boundary_count >= 2:
        matched = max(matched, boundary_count)
    return max(1, matched)


def split_guidance(phase_count: int, limit: int) -> str:
    return (
        "Task is too broad for this model profile. Split it into single-purpose tasks "
        "before retrying. Recommended sequence: inspect current state; perform the fix only; "
        "run sync/build/deploy only after the fix is verified; verify the public result; report status. "
        f"Detected approximately {phase_count} phases; this model profile allows {limit}."
    )


def assess_task_granularity(
    *,
    model_name: str,
    title: str = "",
    description: str = "",
    context: str = "",
    allow_multistage: bool = False,
    honor_allow_multistage: bool = True,
    max_phases: int | None = None,
) -> TaskGranularityDecision:
    capability = capability_for_model(model_name)
    limit = max_phases if max_phases is not None else _phase_limit(capability)
    text = "\n".join(part for part in (title, description, context) if part)
    phase_count = estimate_phase_count(text)

    if (honor_allow_multistage and allow_multistage) or phase_count <= limit:
        return TaskGranularityDecision(
            allowed=True,
            model_name=model_name,
            capability=capability,
            phase_count=phase_count,
            limit=limit,
        )

    guidance = split_guidance(phase_count, limit)
    return TaskGranularityDecision(
        allowed=False,
        model_name=model_name,
        capability=capability,
        phase_count=phase_count,
        limit=limit,
        reason="task_too_broad_for_model",
        guidance=guidance,
    )
