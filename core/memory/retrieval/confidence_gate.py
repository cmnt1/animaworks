from __future__ import annotations

# AnimaWorks - Digital Anima Framework
"""Retrieval confidence gate — abstain when evidence is weak."""

from dataclasses import dataclass
from typing import Any


@dataclass
class GateResult:
    """Output of confidence gating."""

    candidates: list[dict[str, Any]]
    abstain: bool = False
    reason: str = ""
    low_confidence: bool = False


def apply_confidence_gate(
    candidates: list[dict[str, Any]],
    *,
    threshold: float,
    score_field: str = "score",
) -> GateResult:
    """Keep candidates but mark the overall result low-confidence when weak.

    Candidates below *threshold* are not discarded.  ``abstain`` is only True
    when there are genuinely no candidates; otherwise a weak result is passed
    through with ``low_confidence=True`` so callers can show ``[low-confidence]``.
    """
    if not candidates:
        return GateResult(candidates=[], abstain=True, reason="low_confidence", low_confidence=True)

    max_score = max(float(c.get(score_field, 0.0) or 0.0) for c in candidates)
    if max_score < threshold:
        return GateResult(candidates=candidates, abstain=False, low_confidence=True)

    return GateResult(candidates=candidates, abstain=False)
