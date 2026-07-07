"""Task closure contract helpers.

The contract is intentionally small and plain JSON so LLM tasks, cron jobs, and
report generators can share one definition of "done".
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

CONTRACT_KEY = "task_closure"

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_INLINE_CONTRACT_RE = re.compile(r"TASK_CLOSURE\s*:\s*(\{.*\})", re.DOTALL | re.IGNORECASE)


def acceptance_criteria_present(task_desc: Mapping[str, Any]) -> bool:
    criteria = task_desc.get("acceptance_criteria")
    if isinstance(criteria, str):
        return bool(criteria.strip())
    if isinstance(criteria, Iterable):
        return any(bool(str(item).strip()) for item in criteria)
    return False


def closure_required_for_task(task_desc: Mapping[str, Any]) -> bool:
    """Return whether a TaskExec result must include a closure contract."""
    if bool(
        task_desc.get("closure_required")
        or task_desc.get("task_closure_required")
        or task_desc.get("require_task_closure")
    ):
        return True
    return acceptance_criteria_present(task_desc)


def build_task_closure(
    *,
    latest_user_request: str,
    acceptance_checks: Iterable[Mapping[str, Any]],
    remaining_blockers: Iterable[str] | None = None,
    changed_files: Iterable[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    checks = [dict(check) for check in acceptance_checks]
    blockers = [str(item) for item in (remaining_blockers or []) if str(item).strip()]
    blockers.extend(
        str(check.get("name") or "unnamed_check")
        for check in checks
        if str(check.get("status", "")).casefold() != "passed"
    )
    can_submit = not blockers and all(str(check.get("status", "")).casefold() == "passed" for check in checks)
    payload: dict[str, Any] = {
        "latest_user_request": latest_user_request,
        "changed_files": list(changed_files or []),
        "acceptance_checks": checks,
        "remaining_blockers": blockers,
        "can_submit": can_submit,
    }
    if notes:
        payload["notes"] = notes
    return payload


def _decode_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def extract_task_closure(text: str) -> dict[str, Any] | None:
    """Extract a task_closure object from final text.

    Supported forms:
    - fenced JSON containing {"task_closure": {...}}
    - fenced JSON containing the closure object itself
    - TASK_CLOSURE: {"can_submit": true, ...}
    """
    if not text:
        return None

    candidates: list[str] = []
    candidates.extend(match.group(1) for match in _JSON_BLOCK_RE.finditer(text))
    inline = _INLINE_CONTRACT_RE.search(text)
    if inline:
        candidates.append(inline.group(1).strip())

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)

    for candidate in candidates:
        decoded = _decode_json_object(candidate)
        if not decoded:
            continue
        closure = decoded.get(CONTRACT_KEY, decoded)
        if isinstance(closure, dict) and ("can_submit" in closure or "acceptance_checks" in closure):
            return closure
    return None


def closure_block_reason(closure: Mapping[str, Any] | None) -> str | None:
    """Return a human-readable block reason, or None when the contract passes."""
    if closure is None:
        return "Task did not provide a task_closure contract"
    if bool(closure.get("can_submit")) is not True:
        blockers = closure.get("remaining_blockers") or []
        if isinstance(blockers, list) and blockers:
            return "Task closure reports remaining blockers: " + "; ".join(str(item) for item in blockers[:3])
        return "Task closure can_submit is not true"

    checks = closure.get("acceptance_checks")
    if not isinstance(checks, list) or not checks:
        return "Task closure has no acceptance_checks"
    failing = [
        str(check.get("name") or "unnamed_check")
        for check in checks
        if not isinstance(check, Mapping) or str(check.get("status", "")).casefold() != "passed"
    ]
    if failing:
        return "Task closure has failing checks: " + ", ".join(failing[:5])
    return None


def classify_closure_result(result: str, task_desc: Mapping[str, Any]) -> tuple[str, str] | None:
    """Classify a TaskExec result by its closure contract.

    Returns None when no closure contract is required. Otherwise returns a
    queue-style (status, summary) tuple.
    """
    if not closure_required_for_task(task_desc):
        return None
    closure = extract_task_closure(result)
    reason = closure_block_reason(closure)
    if reason:
        return "blocked", f"BLOCKED: {reason}"
    return "done", (result or "")[:200]
