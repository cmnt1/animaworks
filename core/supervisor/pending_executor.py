# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Pending task watcher and executor.

Monitors state/background_tasks/pending/ for tasks submitted via
``animaworks-tool submit`` and dispatches them through
BackgroundTaskManager.  Supports DAG-based parallel execution
for batched tasks submitted via ``submit_tasks`` tool.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.exceptions import ToolExecutionError
from core.i18n import t
from core.platform.processing_lease import (
    is_processing_lease_live,
    processing_lease_path,
    write_processing_lease,
)
from core.taskboard.attention_resolver import resolver_for_anima_dir
from core.taskboard.models import AttentionDecision

if TYPE_CHECKING:
    from core.anima import BackgroundWorkerSlot, DigitalAnima

logger = logging.getLogger(__name__)


class TaskExecError(RuntimeError):
    """Raised when a TaskExec LLM session encounters a non-recoverable error."""


_PENDING_WATCHER_POLL_INTERVAL = 3.0
_LLM_TASK_TTL_HOURS = 24
_PENDING_TASK_SUBPROCESS_TIMEOUT = 1800
_TASK_RESULT_MAX_CHARS = 2000
_TASK_COMPLETE_NOTIFY_MAX_CHARS = 10_000
_PROCESSING_TOUCH_INTERVAL_SECONDS = 600

_SENTINEL_CANCELLED = "(cancelled)"
_SENTINEL_EXPIRED = "(expired)"
_SENTINEL_DEFERRED = "(deferred)"
_SENTINEL_PROVIDER_RATE_LIMIT = "(provider_rate_limit_deferred)"
_PROVIDER_COOLDOWN_FALLBACK_S = 120

_QUEUE_TERMINAL_STATUSES = {"done", "cancelled", "failed"}
_QUEUE_ACTIVE_STATUSES = {"pending", "in_progress", "blocked", "delegated"}
_TASKBOARD_QUEUE_CANCEL_REASONS = {"expired", "archived", "tombstoned"}
_RUNNER_START_SUFFIX = "-runner-start"
_AUTO_RETRY_BLOCKED_SUMMARY_PREFIXES = (
    "BLOCKED: Task reported an explicit follow-up/start step",
    "BLOCKED: Task reported unresolved blockers instead of final evidence",
    "BLOCKED: Task reported known AFF-003 blockers instead of final evidence",
    "BLOCKED: Multi-stage task reported an intermediate/next-step result",
    "BLOCKED: Task produced only a placeholder completion, not final evidence",
    "BLOCKED: Task hit the iteration limit before final evidence",
)
_AUTO_RETRY_NON_FINAL_MAX_RETRIES = 20
_AUTO_RETRY_STREAM_ERROR_MAX_RETRIES = 2
_NON_FINAL_MULTISTAGE_MARKERS = (
    "will proceed",
    "will continue",
    "will start",
    "next action",
    "next step",
    "retry",
    "re-run",
    "rerun",
    "instruction file",
    "handoff",
    "partial",
    "missing final",
    "no final",
    "not final",
    "not complete",
    "machine",
    "進みます",
    "再試行",
    "指示ファイル",
    "未作成",
    "不足",
    "中間ログ",
    "これから",
)
_UNRESOLVED_BLOCKER_MARKERS = (
    "remaining blocker",
    "still blocked",
    "not complete",
    "not done",
    "cannot complete",
    "blocked:",
    "blockers:",
    "policy blocked",
    "read-only",
    "write not allowed",
    "permission denied",
    "rejected: blocked by policy",
    "blocked by policy",
    "filesystem sandbox",
    "file operation remains",
    "remaining work is",
    "remaining work:",
    "not reflected",
    "not applied",
    "未実施",
    "未反映",
    "残作業",
    "権限付き実行",
    "書き込み可能",
    "current failures",
    "failures to fix",
    "failed gate",
    "http 404",
    "-> http 404",
    " image 404",
    "missing images",
    "public_article_images_missing",
    "image_url_invalid",
    "generated_json_forbidden_token",
    "forbidden_public_source_token_present",
)
_STRONG_NON_FINAL_EXACT_MARKERS = (
    "スキーマが確認できました",
    "修正版スクリプトを作成します",
)
_PREREQUISITE_NON_FINAL_MARKERS = (
    "completion_gate",
    "before completing",
    "before the final answer",
    "完了条件を満たす前",
    "必要がある",
    "必要があります",
    "必要です",
)
_STRONG_NON_FINAL_MARKERS = (
    "now i understand",
    "now i have the full picture",
    *_PREREQUISITE_NON_FINAL_MARKERS,
    "let me write",
    "let me create",
    "let me prepare",
    "let me check",
    "let me look",
    "let me inspect",
    "let me investigate",
    "let me run",
    "now let me",
    "i will write",
    "i will create",
    "i will prepare",
    "i will run",
    "i'll write",
    "i'll create",
    "i'll prepare",
    "i'll run",
    "next i will",
    "i will now",
    "i'll now",
    "db connected",
    "db connection worked",
    "stdin pipe",
    "use stdin pipe",
    "using stdin pipe",
    "db接続できた",
    "db接続できました",
    "stdin pipeを使う",
    "stdin pipeを使います",
    "pipeを使う",
    "pipeを使います",
    "まずdb",
    "まず db",
    "まず確認",
    "まず調査",
    "まず実施",
    "証跡を収集します",
    "確認を実施し",
    "状況を確認しました",
    "will proceed",
    "will continue",
    "will start",
    "moving to",
    "switching to direct",
    "machine is unavailable",
    "machine unavailable",
    "次に",
    "これから",
    "進みます",
    "確認します",
    "実行します",
    "移行します",
    "machineが使えない",
    "machine起動不可",
    "直接実行経路",
)


def _is_provider_rate_limit_error(message: str) -> bool:
    text = (message or "").casefold()
    return text.startswith(("rate_limit:", "rate_limit_deferred:")) or "provider rate limit" in text


def _provider_cooldown_until_from_message(message: str) -> datetime:
    match = re.search(r"\buntil=([^\s;]+)", message or "")
    if match:
        try:
            parsed = datetime.fromisoformat(match.group(1))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC) + timedelta(seconds=_PROVIDER_COOLDOWN_FALLBACK_S)


def _provider_cooldown_until_from_task_desc(task_desc: dict[str, Any]) -> datetime | None:
    raw = task_desc.get("_provider_cooldown_until")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _remove_processing_lease(descriptor_path: Path) -> None:
    lease_path = processing_lease_path(descriptor_path)
    try:
        lease_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove processing lease: %s", lease_path, exc_info=True)


def _unlink_processing_descriptor(descriptor_path: Path) -> None:
    descriptor_path.unlink(missing_ok=True)
    _remove_processing_lease(descriptor_path)


def _move_processing_with_lease(
    descriptor_path: Path,
    failed_dir: Path,
    *,
    collision_label: str,
) -> Path:
    """Move a processing descriptor and its sidecar without overwriting."""
    target = _processing_failed_target(
        descriptor_path,
        failed_dir,
        collision_label=collision_label,
    )
    descriptor_path.rename(target)

    lease_path = processing_lease_path(descriptor_path)
    if lease_path.exists():
        try:
            lease_path.rename(processing_lease_path(target))
        except OSError:
            logger.warning("Failed to move processing lease: %s", lease_path, exc_info=True)
    return target


def _processing_failed_target(
    descriptor_path: Path,
    failed_dir: Path,
    *,
    collision_label: str,
) -> Path:
    """Return a collision-safe failed path for a processing descriptor."""
    failed_dir.mkdir(parents=True, exist_ok=True)
    target = failed_dir / descriptor_path.name
    if target.exists():
        timestamp = int(time.time())
        target = failed_dir / f"{descriptor_path.name}.{collision_label}-{timestamp}"
        counter = 1
        while target.exists():
            target = failed_dir / f"{descriptor_path.name}.{collision_label}-{timestamp}-{counter}"
            counter += 1
    return target


def _move_processing_without_lease(
    descriptor_path: Path,
    failed_dir: Path,
    *,
    collision_label: str,
) -> Path:
    """Move a descriptor to failed while leaving its lease for deletion."""
    target = _processing_failed_target(
        descriptor_path,
        failed_dir,
        collision_label=collision_label,
    )
    descriptor_path.rename(target)
    return target


def _task_activity_identity(task_desc: dict[str, Any]) -> tuple[str, str, str]:
    """Return stable task id, title, and description for execution events."""
    task_id = str(task_desc.get("task_id") or "unknown")
    description = str(task_desc.get("description") or "")
    title = str(task_desc.get("title") or "").strip()
    if not title:
        title = next((line.strip() for line in description.splitlines() if line.strip()), "")[:100]
    return task_id, title or task_id, description


def _detect_task_auth_failure(result: str) -> str | None:
    """Return an auth-failure summary when the result is a terminal auth error."""
    text = (result or "").strip()
    if not text:
        return None

    folded = text.casefold()
    auth_markers = (
        "failed to authenticate",
        "invalid authentication credentials",
        "authentication_error",
        "not authenticated",
    )
    if not any(marker in folded for marker in auth_markers):
        return None
    if not any(marker in folded for marker in ("401", "api error", "unauthorized", "auth")):
        return None
    return text[:200]


def _detect_synthesized_tool_failure(result: str) -> str | None:
    """Return a failure summary for SDK fallback text with tool errors only."""
    text = (result or "").strip()
    if not text.startswith("(completed ") or "tool call(s)" not in text:
        return None
    marker = "; errors="
    if marker not in text:
        return None
    try:
        errors_part = text.split(marker, 1)[1].split(")", 1)[0].strip()
        error_count = int(errors_part)
    except (ValueError, IndexError):
        return "Task produced no final response and reported tool errors"
    if error_count <= 0:
        return None
    return f"Task produced no final response and reported {error_count} tool error(s)"


def _detect_synthesized_tool_only_result(result: str) -> str | None:
    """Return a blocked summary when TaskExec only synthesized tool-call counts."""
    text = (result or "").strip()
    if not text.startswith("(completed ") or "tool call(s)" not in text:
        return None
    if "; errors=" in text:
        return None
    return "Task produced only a tool-call summary, not final evidence"


def _detect_placeholder_completion_result(result: str) -> str | None:
    """Return a blocked summary for completion placeholders with no evidence."""
    text = (result or "").strip()
    normalized = text.replace("（", "(").replace("）", ")")
    placeholders = {
        "(タスク完了)",
        "タスク完了",
        "(task complete)",
        "task complete",
        "(task completed)",
        "task completed",
    }
    if normalized.casefold() not in placeholders:
        return None
    return "Task produced only a placeholder completion, not final evidence"


def _detect_iteration_limit_result(result: str) -> str | None:
    """Return a blocked summary when the runner stops before a final answer."""
    text = (result or "").strip().replace("（", "(").replace("）", ")")
    folded = text.casefold()
    if folded in {
        "(max iterations reached)",
        "max iterations reached",
        "(maximum iterations reached)",
        "maximum iterations reached",
    }:
        return "Task hit the iteration limit before final evidence"
    return None


def _task_desc_requires_final_evidence(task_desc: dict[str, Any]) -> bool:
    """Return whether a task descriptor demands concrete final evidence."""
    parts: list[str] = []
    for key in ("title", "description", "context"):
        value = task_desc.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("acceptance_criteria", "constraints", "file_paths"):
        value = task_desc.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    text = "\n".join(parts).casefold()
    evidence_terms = (
        "証跡",
        "全ゲート",
        "ゲート",
        "完了条件",
        "db read-after",
        "read-after",
        "sync/deploy",
        "deploy",
        "公開url",
        "public url",
        "image/*",
        "final evidence",
        "six-gate",
        "6-gate",
    )
    return any(term in text for term in evidence_terms)


def _detect_non_final_delegation_report(result: str) -> str | None:
    """Return a failure summary when TaskExec only reports a handoff/start log."""
    text = (result or "").strip()
    if not text:
        return None

    folded = text.casefold()
    has_machine_handoff = ("machine" in folded or "agent" in folded or "エージェント" in text or "委託" in text) and (
        "委託" in text or "delegat" in folded or "handoff" in folded or "依頼" in text
    )
    if not has_machine_handoff:
        return None

    has_start_only_marker = any(
        marker in text
        for marker in (
            "状況把握",
            "確認開始",
            "着手",
            "進めます",
            "開始します",
        )
    ) or any(
        marker in folded
        for marker in (
            "started",
            "starting",
            "will proceed",
            "will start",
            "checking files",
        )
    )
    if not has_start_only_marker:
        return None

    final_evidence_markers = (
        'verdict.status="done"',
        '"status": "done"',
        '"status":"done"',
        "verifier output",
        "db read-after-write",
        "http 200",
        "image/*",
        "deploy complete",
    )
    evidence_count = sum(1 for marker in final_evidence_markers if marker in folded)
    if evidence_count >= 3:
        return None
    return "Task reported only a machine handoff/start log, not final evidence"


def _completion_evidence_count(text: str) -> int:
    folded = text.casefold()
    final_evidence_markers = (
        'verdict.status="done"',
        '"status": "done"',
        '"status":"done"',
        "verifier output",
        "db read-after-write",
        "http 200",
        "image/*",
        "deploy complete",
    )
    return sum(1 for marker in final_evidence_markers if marker in folded)


def _detect_unresolved_blocker_report(result: str) -> str | None:
    """Return a blocked summary when a report lists unresolved gates as its result."""
    text = (result or "").strip()
    if not text:
        return None

    folded = text.casefold()
    if _completion_evidence_count(text) >= 3:
        return None

    if any(marker in folded for marker in _UNRESOLVED_BLOCKER_MARKERS):
        return "Task reported unresolved blockers instead of final evidence"

    target_ids = ("108500", "108501", "108502")
    known_blocker_tokens = ("404", "4axjkd+4bf3ma+5316", "coreda")
    if any(task_id in text for task_id in target_ids) and any(token in folded for token in known_blocker_tokens):
        return "Task reported known AFF-003 blockers instead of final evidence"

    return None


def _detect_non_final_multistage_result(result: str) -> str | None:
    """Return a blocked summary when a multi-stage task reports a next step."""
    text = (result or "").strip()
    if not text or _completion_evidence_count(text) >= 3:
        return None

    folded = text.casefold()
    if any(marker in folded for marker in _NON_FINAL_MULTISTAGE_MARKERS):
        return "Multi-stage task reported an intermediate/next-step result, not final evidence"
    return None


def _detect_strong_non_final_followup(result: str) -> str | None:
    """Return a blocked summary for explicit follow-up/start reports."""
    text = (result or "").strip()
    if not text or _completion_evidence_count(text) >= 3:
        return None

    folded = text.casefold()
    if any(marker in text for marker in _STRONG_NON_FINAL_EXACT_MARKERS):
        return "Task reported an explicit follow-up/start step, not final evidence"
    if any(marker in folded for marker in _STRONG_NON_FINAL_MARKERS):
        return "Task reported an explicit follow-up/start step, not final evidence"
    return None


def _detect_non_final_prerequisite_report(result: str) -> str | None:
    text = (result or "").strip()
    if not text or _completion_evidence_count(text) >= 3:
        return None

    folded = text.casefold()
    if any(marker in folded for marker in _PREREQUISITE_NON_FINAL_MARKERS):
        return "Task reported an explicit follow-up/start step, not final evidence"
    return None


def _classify_task_result(result: str) -> tuple[str, str]:
    """Map _run_llm_task return value to (queue_status, summary).

    Uses only statuses defined in ``task_queue._VALID_STATUSES``.
    """
    if result == _SENTINEL_CANCELLED:
        return "cancelled", "cancelled before execution"
    if result == _SENTINEL_EXPIRED:
        return "cancelled", "expired (TTL exceeded)"
    if result == _SENTINEL_DEFERRED:
        return "pending", "snoozed by TaskBoard"
    if result == _SENTINEL_PROVIDER_RATE_LIMIT:
        return "pending", t("pending_executor.provider_rate_limit_deferred")
    auth_failure = _detect_task_auth_failure(result)
    if auth_failure:
        return "failed", f"FAILED: {auth_failure}"
    synthesized_failure = _detect_synthesized_tool_failure(result)
    if synthesized_failure:
        return "failed", f"FAILED: {synthesized_failure}"
    non_final_delegation = _detect_non_final_delegation_report(result)
    if non_final_delegation:
        return "blocked", f"BLOCKED: {non_final_delegation}"
    unresolved_blocker = _detect_unresolved_blocker_report(result)
    if unresolved_blocker:
        return "blocked", f"BLOCKED: {unresolved_blocker}"
    prerequisite = _detect_non_final_prerequisite_report(result)
    if prerequisite:
        return "blocked", f"BLOCKED: {prerequisite}"
    return "done", (result or "")[:200]


def _classify_task_result_for_desc(result: str, task_desc: dict[str, Any]) -> tuple[str, str]:
    """Classify a task result with task descriptor context."""
    status, summary = _classify_task_result(result)
    if status != "done":
        return status, summary
    iteration_limit = _detect_iteration_limit_result(result)
    if iteration_limit:
        return "blocked", f"BLOCKED: {iteration_limit}"
    non_final = _detect_non_final_multistage_result(result)
    if non_final and bool(task_desc.get("allow_multistage")):
        return "blocked", f"BLOCKED: {non_final}"
    strong_followup = _detect_strong_non_final_followup(result)
    if strong_followup:
        return "blocked", f"BLOCKED: {strong_followup}"
    tool_only = _detect_synthesized_tool_only_result(result)
    if tool_only:
        return "blocked", f"BLOCKED: {tool_only}"
    placeholder = _detect_placeholder_completion_result(result)
    if placeholder and _task_desc_requires_final_evidence(task_desc):
        return "blocked", f"BLOCKED: {placeholder}"
    try:
        from core.task_closure import classify_closure_result

        closure_result = classify_closure_result(result, task_desc)
    except Exception:
        logger.debug("pending_executor: task closure classification skipped", exc_info=True)
        closure_result = None
    if closure_result is not None:
        return closure_result
    return status, summary


def _blocked_summary_allows_retry(summary: str | None) -> bool:
    text = (summary or "").strip()
    return any(text.startswith(prefix) for prefix in _AUTO_RETRY_BLOCKED_SUMMARY_PREFIXES)


def _command_queue_link(task_id: str, tool_name: str, subcommand: str) -> tuple[str, str, str] | None:
    """Return (queue_task_id, success_status, failure_status) for command tasks.

    Dashboard runner-start commands are child pending tasks. Their success only
    means the external runner was launched, so the parent queue task should move
    to in_progress rather than done.
    """
    if not task_id:
        return None
    if tool_name == "daily_ops_runner" and subcommand == "start" and task_id.endswith(_RUNNER_START_SUFFIX):
        return task_id[: -len(_RUNNER_START_SUFFIX)], "in_progress", "blocked"
    return task_id, "done", "blocked"


def _resolve_default_workspace(anima_dir: Path) -> str:
    """Resolve default_workspace from status.json via workspace registry.

    Returns absolute path string, or empty string if not set or resolution fails.
    """
    from core.workspace import resolve_default_workspace

    resolved, _alias = resolve_default_workspace(anima_dir)
    return resolved.as_posix() if resolved else ""


# ── DAG helpers ──────────────────────────────────────────────


def _topological_sort(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return tasks in topological order. Raises ValueError on cycles."""
    task_map = {td["task_id"]: td for td in tasks}
    in_degree: dict[str, int] = {tid: 0 for tid in task_map}
    for td in tasks:
        for dep in td.get("depends_on", []):
            if dep in in_degree:
                in_degree[td["task_id"]] += 1

    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    result: list[dict[str, Any]] = []
    while queue:
        tid = queue.pop(0)
        result.append(task_map[tid])
        for td in tasks:
            if tid in td.get("depends_on", []):
                in_degree[td["task_id"]] -= 1
                if in_degree[td["task_id"]] == 0:
                    queue.append(td["task_id"])

    if len(result) != len(tasks):
        raise ValueError("Cycle detected in task dependencies")
    return result


def _deps_satisfied(
    task: dict[str, Any],
    completed: dict[str, str],
    failed: set[str],
) -> bool:
    """Check if all dependencies are either completed or failed."""
    for dep in task.get("depends_on", []):  # noqa: SIM110
        if dep not in completed and dep not in failed:
            return False
    return True


def _dependency_failure_reason(task: dict[str, Any], attention_suppressed: set[str]) -> str:
    if any(dep in attention_suppressed for dep in task.get("depends_on", [])):
        return "dependency_suppressed"
    return "failed_dependency"


class PendingTaskExecutor:
    """Watch pending/ directory and execute submitted tasks."""

    def __init__(
        self,
        anima: DigitalAnima,
        anima_name: str,
        anima_dir: Path,
        shutdown_event: asyncio.Event,
    ) -> None:
        self._anima = anima
        self._anima_name = anima_name
        self._anima_dir = anima_dir
        self._shutdown_event = shutdown_event
        self._wake_event = asyncio.Event()
        self._batch_tasks: dict[str, list[dict[str, Any]]] = {}
        self._active_dispatch_tasks: set[asyncio.Task[None]] = set()
        self._active_task_ids: set[str] = set()
        self._batch_dispatch_lock = asyncio.Lock()
        self._workspace_locks: dict[Path, asyncio.Lock] = {}

    def _worker_pool_size(self) -> int:
        """Return a validated pool size while tolerating legacy test doubles."""
        value = getattr(self._anima, "_background_worker_pool_size", 1)
        return value if isinstance(value, int) and 1 <= value <= 10 else 1

    def _workspace_key(self, task_desc: dict[str, Any]) -> Path:
        """Resolve the workspace used for write-task mutual exclusion."""
        workspace = task_desc.get("working_directory", "") or _resolve_default_workspace(self._anima_dir)
        return Path(workspace or self._anima_dir).expanduser().resolve()

    def _workspace_lock(self, task_desc: dict[str, Any]) -> asyncio.Lock | None:
        """Return the exclusion lock for the task's explicit workspace.

        Tasks without an explicit ``working_directory`` pick their own working
        area at runtime (e.g. per-task worktrees), so they are not serialized
        against each other.
        """
        if not task_desc.get("working_directory"):
            return None
        key = self._workspace_key(task_desc)
        lock = self._workspace_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._workspace_locks[key] = lock
        return lock

    async def _acquire_worker(self, task_id: str) -> BackgroundWorkerSlot | None:
        acquire = getattr(type(self._anima), "_acquire_background_worker", None)
        if callable(acquire):
            return await self._anima._acquire_background_worker(task_id)
        return None

    async def _release_worker(self, slot: BackgroundWorkerSlot | None) -> None:
        if slot is None:
            return
        release = getattr(type(self._anima), "_release_background_worker", None)
        if callable(release):
            await self._anima._release_background_worker(slot)

    def _track_dispatch_task(self, task: asyncio.Task[None]) -> None:
        """Keep a strong reference to a detached single-task dispatch."""
        self._active_dispatch_tasks.add(task)

        def _done(done: asyncio.Task[None]) -> None:
            self._active_dispatch_tasks.discard(done)
            self.wake()

        task.add_done_callback(_done)

    def _claim_processing_task(
        self,
        processing_path: Path,
        failed_dir: Path,
        task_desc: dict[str, Any],
    ) -> str | None:
        """Create a lease and register a task id, quarantining duplicates."""
        task_id = str(task_desc.get("task_id") or processing_path.stem).strip()
        try:
            write_processing_lease(
                processing_path,
                anima=self._anima_name,
                task_id=task_id,
            )
        except OSError:
            logger.exception("Failed to create processing lease: %s", processing_path.name)
            try:
                _move_processing_with_lease(
                    processing_path,
                    failed_dir,
                    collision_label="lease-error",
                )
            except OSError:
                logger.exception("Failed to quarantine unleased task: %s", processing_path.name)
            return None

        if task_id in self._active_task_ids:
            logger.warning("Duplicate task_id claim rejected: %s", task_id)
            try:
                _move_processing_with_lease(
                    processing_path,
                    failed_dir,
                    collision_label="dup",
                )
            except OSError:
                logger.exception("Failed to quarantine duplicate task: %s", processing_path.name)
            return None

        self._active_task_ids.add(task_id)
        return task_id

    async def _touch_processing_descriptor(self, processing_path: Path) -> None:
        """Keep a long-running processing descriptor younger than housekeeping."""
        while True:
            await asyncio.sleep(_PROCESSING_TOUCH_INTERVAL_SECONDS)
            try:
                os.utime(processing_path, None)
            except FileNotFoundError:
                return
            except OSError:
                logger.warning("Failed to touch processing task: %s", processing_path, exc_info=True)

    def _track_command_claim(
        self,
        background_task: asyncio.Task[None],
        *,
        task_id: str,
        processing_path: Path,
        failed_dir: Path,
    ) -> None:
        """Keep a command claim active until BackgroundTaskManager finishes it."""
        touch_task = asyncio.create_task(
            self._touch_processing_descriptor(processing_path),
            name=f"task-touch-{self._anima_name}-{task_id}",
        )

        def _done(done: asyncio.Task[None]) -> None:
            touch_task.cancel()
            try:
                if done.cancelled():
                    _move_processing_without_lease(
                        processing_path,
                        failed_dir,
                        collision_label="cancelled",
                    )
                else:
                    _unlink_processing_descriptor(processing_path)
            except OSError:
                logger.warning("Failed to finalize command task file: %s", processing_path, exc_info=True)
            finally:
                _remove_processing_lease(processing_path)
                self._active_task_ids.discard(task_id)
                self.wake()

        background_task.add_done_callback(_done)

    # ── Semaphore lazy init ──────────────────────────────────

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Get or create the task semaphore from config."""
        if self._anima._task_semaphore is None:
            try:
                from core.config.models import load_config

                config = load_config()
                max_parallel = config.background_task.max_parallel_llm_tasks
            except Exception:
                max_parallel = 3
            self._anima._task_semaphore = asyncio.Semaphore(max_parallel)
        return self._anima._task_semaphore

    # ── Result save / dependency context ─────────────────────

    def _save_task_result(self, task_id: str, summary: str) -> None:
        """Save task result summary to state/task_results/{task_id}.md."""
        results_dir = self._anima_dir / "state" / "task_results"
        results_dir.mkdir(parents=True, exist_ok=True)
        path = results_dir / f"{task_id}.md"
        truncated = summary[:_TASK_RESULT_MAX_CHARS]
        path.write_text(truncated, encoding="utf-8")

    def _build_dependency_context(
        self,
        task_desc: dict[str, Any],
        completed: dict[str, str],
    ) -> str:
        """Build context from completed dependency results."""
        parts: list[str] = []
        for dep_id in task_desc.get("depends_on", []):
            result = completed.get(dep_id, "")
            if result:
                parts.append(t("pending_executor.dep_result_header", dep_id=dep_id) + f"\n{result}")
        return "\n\n".join(parts)

    def _write_failed_result(self, task_id: str, reason: str) -> None:
        """Write a failure marker for a task."""
        self._save_task_result(task_id, f"FAILED: {reason}")

    def _sync_task_queue(
        self,
        task_id: str,
        status: str,
        *,
        summary: str | None = None,
        note: str | None = None,
    ) -> None:
        """Sync task status to task_queue.jsonl (Layer 2).

        Silently skips if the task is not registered in task_queue
        (e.g., legacy tasks created before this sync was implemented).
        """
        try:
            from core.memory.task_queue import TaskQueueManager

            manager = TaskQueueManager(self._anima_dir)
            entry = manager.get_task_by_id(task_id)
            if entry and entry.status in _QUEUE_TERMINAL_STATUSES:
                if status != entry.status:
                    logger.info(
                        "[%s] Skipping task_queue sync for terminal task %s: current=%s incoming=%s",
                        self._anima_name,
                        task_id,
                        entry.status,
                        status,
                    )
                return
            manager.update_status(task_id, status, summary=summary, note=note)
        except Exception:
            logger.warning(
                "[%s] Failed to sync task %s status=%s to task_queue",
                self._anima_name,
                task_id,
                status,
                exc_info=True,
            )

    def _auto_retry_blocked_llm_task(self, task_desc: dict[str, Any]) -> bool:
        """Requeue executable multi-stage tasks that ended in a blocked report."""
        task_id = task_desc.get("task_id", "")
        if not task_id:
            return False

        entry = self._get_task_queue_entry(task_id)
        if entry is None or entry.status != "blocked":
            return False

        meta = entry.meta or {}
        task_desc_meta = meta.get("task_desc") if isinstance(meta.get("task_desc"), dict) else {}
        if not (
            bool(task_desc.get("allow_multistage"))
            or bool(task_desc_meta.get("allow_multistage"))
            or bool(meta.get("auto_retry_on_blocked"))
            or _blocked_summary_allows_retry(entry.summary)
        ):
            return False

        if bool(meta.get("needs_human")):
            logger.info("[%s] Blocked task requires human input; not auto-retrying: %s", self._anima_name, task_id)
            return False

        submitted_by = task_desc.get("submitted_by")
        if not isinstance(submitted_by, str) or not submitted_by:
            submitted_by = self._anima_name

        try:
            from core.supervisor.task_retry import TaskRetryError, retry_task

            max_retries = _AUTO_RETRY_NON_FINAL_MAX_RETRIES if _blocked_summary_allows_retry(entry.summary) else None
            retry_kwargs: dict[str, Any] = {
                "summary": "auto retry queued after blocked TaskExec result",
                "submitted_by": submitted_by,
            }
            if max_retries is not None:
                retry_kwargs["max_retries"] = max_retries
            retry_task(
                self._anima_dir,
                task_id,
                **retry_kwargs,
            )
            self.wake()
            logger.info("[%s] Auto-requeued blocked multi-stage task: %s", self._anima_name, task_id)
            return True
        except TaskRetryError:
            logger.info("[%s] Blocked task not auto-requeued: %s", self._anima_name, task_id, exc_info=True)
            return False
        except Exception:
            logger.warning("[%s] Failed to auto-requeue blocked task: %s", self._anima_name, task_id, exc_info=True)
            return False

    def _sweep_auto_retryable_blocked_llm_tasks(self) -> int:
        """Requeue stale blocked TaskExec rows that qualify for automatic retry."""
        try:
            from core.memory.task_queue import TaskQueueManager

            manager = TaskQueueManager(self._anima_dir)
            entries = manager.list_tasks(status="blocked")
        except Exception:
            logger.warning("[%s] Failed to list blocked tasks for auto-retry sweep", self._anima_name, exc_info=True)
            return 0

        retried = 0
        for entry in entries:
            meta = entry.meta or {}
            task_desc_meta = meta.get("task_desc")
            task_desc = dict(task_desc_meta) if isinstance(task_desc_meta, dict) else {}
            if not (
                bool(task_desc.get("allow_multistage"))
                or bool(meta.get("allow_multistage"))
                or bool(meta.get("auto_retry_on_blocked"))
                or _blocked_summary_allows_retry(entry.summary)
            ):
                continue
            task_desc.setdefault("task_type", "llm")
            task_desc["task_id"] = entry.task_id
            task_desc.setdefault("description", entry.original_instruction)
            if self._auto_retry_blocked_llm_task(task_desc):
                retried += 1
        if retried:
            logger.info("[%s] Auto-retry sweep requeued %d blocked TaskExec task(s)", self._anima_name, retried)
        return retried

    def _get_task_queue_entry(self, task_id: str) -> Any | None:
        if not task_id:
            return None
        try:
            from core.memory.task_queue import TaskQueueManager

            return TaskQueueManager(self._anima_dir).get_task_by_id(task_id)
        except Exception:
            logger.debug(
                "Could not check task_queue for task: %s",
                task_id,
                exc_info=True,
            )
            return None

    def _auto_requeue_stream_error_llm_task(self, task_desc: dict[str, Any], exc: Exception) -> bool:
        """Requeue transient TaskExec stream disconnects before terminal failure."""
        task_id = task_desc.get("task_id", "")
        if not task_id or not isinstance(exc, TaskExecError):
            return False

        reason = str(exc)
        folded = reason.casefold()
        if "streaming error" not in folded and "stream disconnected" not in folded:
            return False

        try:
            from core.memory.task_queue import TaskQueueManager

            manager = TaskQueueManager(self._anima_dir)
            entry = manager.get_task_by_id(task_id)
            if entry is None:
                return False

            meta = dict(entry.meta or {})
            retry_count = int(meta.get("stream_error_retry_count") or 0)
            if retry_count >= _AUTO_RETRY_STREAM_ERROR_MAX_RETRIES:
                return False
            retry_count += 1
            meta["stream_error_retry_count"] = retry_count
            manager.update_meta(task_id, meta)

            pending_dir = self._anima_dir / "state" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            retried_desc = dict(task_desc)
            retried_desc["_stream_error_retry_count"] = retry_count
            (pending_dir / f"{task_id}.json").write_text(
                json.dumps(retried_desc, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            manager.update_status(
                task_id,
                "pending",
                summary="Stream error retry queued",
                note=(f"TaskExec streaming error retry {retry_count}/{_AUTO_RETRY_STREAM_ERROR_MAX_RETRIES}"),
            )
            self.wake()
            logger.info(
                "[%s] Requeued TaskExec stream error: id=%s retry=%d/%d",
                self._anima_name,
                task_id,
                retry_count,
                _AUTO_RETRY_STREAM_ERROR_MAX_RETRIES,
            )
            return True
        except Exception:
            logger.warning(
                "[%s] Failed to requeue TaskExec stream error: id=%s",
                self._anima_name,
                task_id,
                exc_info=True,
            )
            return False

    def _format_active_sibling_tasks(
        self,
        current_task_id: str,
        *,
        limit: int = 8,
    ) -> str:
        """Format one-line summaries of other in_progress tasks for prompt injection.

        Gives each worker visibility into what sibling workers of the same
        anima are doing, so it can avoid touching the same PR/branch/resource.
        Returns an empty string when there are no siblings.
        """
        try:
            from core.memory.task_queue import TaskQueueManager

            entries = TaskQueueManager(self._anima_dir).list_tasks(status="in_progress")
        except Exception:
            logger.debug(
                "Could not list sibling tasks for: %s",
                current_task_id,
                exc_info=True,
            )
            return ""
        lines: list[str] = []
        for entry in entries:
            if entry.task_id == current_task_id:
                continue
            summary = (entry.summary or "").strip()
            summary = summary.splitlines()[0] if summary else "-"
            if len(summary) > 160:
                summary = summary[:160] + "..."
            updated = (entry.updated_at or "")[:16]
            lines.append(f"- [{entry.task_id[:8]}] {summary} ({updated})")
            if len(lines) >= limit:
                break
        return "\n".join(lines)

    async def _handle_goal_completion(self, task_desc: dict[str, Any], result_summary: str) -> None:
        """Run persistent-goal judging after a TaskExec task has completed."""
        task_id = task_desc.get("task_id", "")
        if not task_id:
            return
        try:
            from core.goals import GoalJudge, GoalManager
            from core.memory.task_queue import TaskQueueManager

            entry = TaskQueueManager(self._anima_dir).get_task_by_id(task_id)
            meta = entry.meta if entry is not None else {}
            goal_id = str(meta.get("goal_id") or task_desc.get("goal_id") or "").strip()
            if not goal_id:
                return

            manager = GoalManager(self._anima_dir)
            state = manager.get_goal(goal_id)
            if state is None or state.status != "active":
                return

            judge = GoalJudge(
                self._anima_dir,
                judge_fn=getattr(self, "_goal_judge_fn", None),
            )
            judgment = await judge.judge(
                state,
                task_id=task_id,
                result_summaries=[result_summary],
                verification_output=str(task_desc.get("verification_output") or ""),
            )
            updated = manager.record_judgment(
                goal_id,
                judgment,
                result_summary=result_summary,
                actor="goal_judge",
            )
            if updated is None or updated.last_judgment is None:
                return

            actual = updated.last_judgment
            if actual.verdict == "done":
                manager.mark_done_activity(updated)
                return
            if actual.verdict == "blocked":
                manager.mark_blocked_activity(updated)
                await self._notify_goal_blocked(updated)
                return
            if actual.verdict == "continue":
                continuation = manager.enqueue_continuation(
                    goal_id,
                    actual,
                    source_task_desc=task_desc,
                    result_summary=result_summary,
                    respect_human_priority=True,
                )
                if continuation is not None:
                    self.wake()
        except Exception:
            logger.warning(
                "[%s] Goal completion hook failed for task %s",
                self._anima_name,
                task_id,
                exc_info=True,
            )

    async def _notify_goal_blocked(self, state: Any) -> None:
        """Best-effort human notification for blocked persistent goals."""
        try:
            agent = getattr(self._anima, "agent", None)
            notifier = getattr(agent, "human_notifier", None)
            if notifier is None:
                return
            reason = state.blocked_reason or (state.last_judgment.reason if state.last_judgment else "")
            await notifier.notify(
                f"Goal blocked: {state.title or state.goal_id}",
                reason or state.objective,
                "high",
                anima_name=self._anima_name,
            )
        except Exception:
            logger.debug("[%s] Goal blocked notification failed", self._anima_name, exc_info=True)

    def _pending_json_age_hours(
        self,
        task_desc: dict[str, Any],
        source_path: Path | None,
        now_utc: datetime,
    ) -> float | None:
        submitted_at = task_desc.get("submitted_at")
        if submitted_at:
            try:
                submitted = datetime.fromisoformat(str(submitted_at))
                if submitted.tzinfo is None:
                    submitted = submitted.replace(tzinfo=UTC)
                return (now_utc - submitted.astimezone(UTC)).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        if source_path is not None:
            try:
                modified_at = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
                return (now_utc - modified_at).total_seconds() / 3600
            except OSError:
                return None
        return None

    def _attention_decision_for_task_desc(
        self,
        task_desc: dict[str, Any],
        *,
        source_path: Path | None = None,
        now: datetime | None = None,
    ) -> AttentionDecision:
        task_id = task_desc.get("task_id", "")
        if not task_id:
            return AttentionDecision(reason="active")

        entry = self._get_task_queue_entry(task_id)
        queue_status = entry.status if entry is not None else None
        try:
            decision = resolver_for_anima_dir(self._anima_dir).should_execute(
                self._anima_name,
                task_id,
                queue_status=queue_status,
                now=now,
            )
        except Exception:
            logger.warning(
                "[%s] TaskBoard execution gate unavailable for task %s; failing open",
                self._anima_name,
                task_id,
                exc_info=True,
            )
            if queue_status in _QUEUE_TERMINAL_STATUSES:
                return AttentionDecision(
                    visible_in_prompt=False, executable=False, notify_allowed=False, reason="terminal"
                )
            return AttentionDecision(reason="active")

        if decision.executable and entry is None:
            resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
            age_hours = self._pending_json_age_hours(task_desc, source_path, resolved_now)
            if age_hours is not None and age_hours > _LLM_TASK_TTL_HOURS:
                return AttentionDecision(
                    visible_in_prompt=False,
                    executable=False,
                    notify_allowed=False,
                    reason="queue_missing_stale",
                )

        return decision

    def _cancel_queue_for_attention(self, task_id: str, reason: str) -> None:
        if reason not in _TASKBOARD_QUEUE_CANCEL_REASONS:
            return
        entry = self._get_task_queue_entry(task_id)
        if entry and entry.status in _QUEUE_ACTIVE_STATUSES:
            self._sync_task_queue(task_id, "cancelled", summary=f"{reason} by TaskBoard")

    def _write_deferred_task_json(self, task_desc: dict[str, Any]) -> None:
        task_id = task_desc.get("task_id", "")
        if not task_id:
            return
        deferred_dir = self._anima_dir / "state" / "pending" / "deferred"
        deferred_dir.mkdir(parents=True, exist_ok=True)
        path = deferred_dir / f"{task_id}.json"
        path.write_text(json.dumps(task_desc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.info("[%s] Deferred snoozed LLM task: id=%s", self._anima_name, task_id)

    def _move_attention_gated_file(
        self,
        path: Path,
        target_dir: Path,
        failed_dir: Path,
        *,
        task_id: str,
        reason: str,
    ) -> bool:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / path.name
            if target.exists():
                target.unlink()
            path.rename(target)
            logger.info(
                "[%s] Moved attention-gated pending task %s to %s (reason=%s)",
                self._anima_name,
                task_id,
                target_dir.name,
                reason,
            )
            return True
        except OSError:
            logger.exception(
                "[%s] Failed to move attention-gated task %s to %s",
                self._anima_name,
                task_id,
                target_dir,
            )
            try:
                failed_dir.mkdir(parents=True, exist_ok=True)
                failed = failed_dir / path.name
                if failed.exists():
                    failed.unlink()
                path.rename(failed)
            except OSError:
                logger.exception(
                    "[%s] Failed to move attention-gated task %s to failed/",
                    self._anima_name,
                    task_id,
                )
            self._sync_task_queue(task_id, "failed", summary="FAILED: attention_move_failed")
            return False

    def _handle_llm_attention_gate(
        self,
        path: Path,
        task_desc: dict[str, Any],
        *,
        deferred_dir: Path,
        suppressed_dir: Path,
        failed_dir: Path,
    ) -> bool:
        task_id = task_desc.get("task_id", "")
        decision = self._attention_decision_for_task_desc(task_desc, source_path=path)
        if decision.executable:
            return True

        task_desc["_attention_suppressed_reason"] = decision.reason
        if decision.reason == "snoozed":
            self._move_attention_gated_file(path, deferred_dir, failed_dir, task_id=task_id, reason=decision.reason)
            return False

        self._cancel_queue_for_attention(task_id, decision.reason)
        self._move_attention_gated_file(path, suppressed_dir, failed_dir, task_id=task_id, reason=decision.reason)
        return False

    def _restore_deferred_tasks(
        self,
        deferred_dir: Path,
        pending_dir: Path,
        suppressed_dir: Path,
        failed_dir: Path,
    ) -> None:
        for path in sorted(deferred_dir.glob("*.json")):
            try:
                task_desc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in deferred LLM task file: %s", path.name)
                self._move_attention_gated_file(path, failed_dir, failed_dir, task_id=path.stem, reason="invalid_json")
                continue

            task_id = task_desc.get("task_id", path.stem)
            provider_cooldown_until = _provider_cooldown_until_from_task_desc(task_desc)
            if provider_cooldown_until is not None and datetime.now(UTC) < provider_cooldown_until:
                continue
            decision = self._attention_decision_for_task_desc(task_desc, source_path=path)
            if decision.executable:
                self._move_attention_gated_file(path, pending_dir, failed_dir, task_id=task_id, reason="snooze_elapsed")
            elif decision.reason != "snoozed":
                self._cancel_queue_for_attention(task_id, decision.reason)
                self._move_attention_gated_file(
                    path,
                    suppressed_dir,
                    failed_dir,
                    task_id=task_id,
                    reason=decision.reason,
                )

    # ── Watcher loop ─────────────────────────────────────────

    @staticmethod
    def _recover_processing(
        processing_dir: Path,
        destination_dir: Path,
        anima_dir: Path | None = None,
        *,
        conflict_dir: Path | None = None,
        task_queue_status: str | None = "failed",
    ) -> list[str]:
        """Move orphaned files from processing/ on startup and return task IDs."""
        recovered_task_ids: list[str] = []
        if not processing_dir.exists():
            return recovered_task_ids
        active_statuses = {"pending", "in_progress", "blocked", "delegated"}
        for orphan in sorted(processing_dir.glob("*.json")):
            expected_anima = anima_dir.name if anima_dir is not None else None
            if is_processing_lease_live(orphan, expected_anima=expected_anima):
                logger.warning(
                    "live lease detected, skipping recovery: %s",
                    orphan.name,
                )
                continue
            task_id = orphan.stem
            try:
                task_desc = json.loads(orphan.read_text(encoding="utf-8"))
                raw_task_id = task_desc.get("task_id")
                if isinstance(raw_task_id, str) and raw_task_id:
                    task_id = raw_task_id
            except Exception:
                logger.debug("Failed to read orphaned processing task id: %s", orphan.name, exc_info=True)
            try:
                target = destination_dir / orphan.name
                if target.exists():
                    collision_dir = conflict_dir or destination_dir
                    collision_dir.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                    target = collision_dir / f"{orphan.stem}.orphan-{stamp}{orphan.suffix}"
                    counter = 1
                    while target.exists():
                        target = collision_dir / f"{orphan.stem}.orphan-{stamp}-{counter}{orphan.suffix}"
                        counter += 1
                orphan.rename(target)
                lease_path = processing_lease_path(orphan)
                if lease_path.exists():
                    try:
                        lease_path.rename(processing_lease_path(target))
                    except OSError:
                        logger.warning("Failed to move processing lease: %s", lease_path, exc_info=True)
                recovered_task_ids.append(task_id)
                logger.warning("Recovered orphaned processing task: %s -> %s", orphan.name, target.name)
            except OSError:
                logger.exception("Failed to recover orphaned task: %s", orphan.name)
                continue
            if anima_dir is not None and task_id and task_queue_status is not None:
                try:
                    from core.memory.task_queue import TaskQueueManager

                    manager = TaskQueueManager(anima_dir)
                    entry = manager.get_task_by_id(task_id)
                    if entry is not None and entry.status in active_statuses:
                        manager.update_status(
                            task_id,
                            task_queue_status,
                            summary=(
                                "INTERRUPTED: task was interrupted by a restart and may have "
                                "PARTIALLY EXECUTED (commits/messages may already exist). Verify "
                                "actual completion state before re-delegating."
                            ),
                        )
                except Exception:
                    logger.exception(
                        "Failed to sync Layer2 task_queue for recovered task: %s",
                        task_id,
                    )
        return recovered_task_ids

    async def _execute_claimed_llm_task(
        self,
        task_desc: dict[str, Any],
        processing_path: Path,
        failed_dir: Path,
        worker_slot: BackgroundWorkerSlot | None,
    ) -> None:
        """Run a claimed single LLM task without blocking the coordinator."""
        task_id = str(task_desc.get("task_id") or processing_path.stem).strip()
        touch_task = asyncio.create_task(
            self._touch_processing_descriptor(processing_path),
            name=f"task-touch-{self._anima_name}-{task_id}",
        )
        try:
            await self.execute_pending_task(task_desc, worker_slot=worker_slot)
            _unlink_processing_descriptor(processing_path)
            self._auto_retry_blocked_llm_task(task_desc)
        except asyncio.CancelledError:
            try:
                _move_processing_without_lease(
                    processing_path,
                    failed_dir,
                    collision_label="cancelled",
                )
            except OSError:
                logger.exception("Failed to move cancelled task to failed: %s", processing_path.name)
            raise
        except Exception:
            logger.exception("Error processing LLM pending task file: %s", processing_path.name)
            try:
                _move_processing_without_lease(
                    processing_path,
                    failed_dir,
                    collision_label="failed",
                )
            except OSError:
                logger.exception("Failed to move task to failed: %s", processing_path.name)
        finally:
            touch_task.cancel()
            await asyncio.gather(touch_task, return_exceptions=True)
            _remove_processing_lease(processing_path)
            self._active_task_ids.discard(task_id)
            # A pre-leased slot is normally released by _execute_llm_task.  If
            # dispatch was cancelled before it entered that method, release it here.
            active = getattr(self._anima, "_active_background_workers", {})
            if (
                worker_slot is not None
                and isinstance(active, dict)
                and active.get(worker_slot.slot_id) == task_desc.get("task_id")
            ):
                await self._release_worker(worker_slot)

    async def _execute_claimed_batch(
        self,
        batch_id: str,
        tasks: list[dict[str, Any]],
    ) -> None:
        """Dispatch one accepted batch while retaining its active task ids."""
        try:
            # Preserve the historical one-batch-at-a-time behavior while the
            # watcher remains free to reject duplicate descriptors.
            async with self._batch_dispatch_lock:
                await self._dispatch_batch(batch_id, tasks)
        finally:
            self._active_task_ids.difference_update(str(task.get("task_id") or "").strip() for task in tasks)

    async def watcher_loop(self) -> None:
        """Watch state/background_tasks/pending/ for submitted tasks.

        Tasks submitted via ``animaworks-tool submit`` are picked up here
        and executed through BackgroundTaskManager, outside the Anima lock.
        Batch tasks (with ``batch_id``) are grouped and dispatched via the
        DAG scheduler for parallel execution.

        File lifecycle: pending/ → processing/ → success: delete | fail: failed/
        """
        pending_dir = self._anima_dir / "state" / "background_tasks" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        cmd_processing_dir = pending_dir / "processing"
        cmd_processing_dir.mkdir(exist_ok=True)
        cmd_failed_dir = pending_dir / "failed"
        cmd_failed_dir.mkdir(exist_ok=True)

        llm_pending_dir = self._anima_dir / "state" / "pending"
        llm_pending_dir.mkdir(parents=True, exist_ok=True)
        llm_processing_dir = llm_pending_dir / "processing"
        llm_processing_dir.mkdir(exist_ok=True)
        llm_failed_dir = llm_pending_dir / "failed"
        llm_failed_dir.mkdir(exist_ok=True)
        llm_deferred_dir = llm_pending_dir / "deferred"
        llm_deferred_dir.mkdir(exist_ok=True)
        llm_suppressed_dir = llm_pending_dir / "suppressed"
        llm_suppressed_dir.mkdir(exist_ok=True)

        self._recover_processing(cmd_processing_dir, cmd_failed_dir, anima_dir=self._anima_dir)
        recovered_llm_task_ids = self._recover_processing(
            llm_processing_dir,
            llm_pending_dir,
            conflict_dir=llm_failed_dir,
            task_queue_status=None,
        )
        for task_id in recovered_llm_task_ids:
            self._sync_task_queue(task_id, "pending", note="Recovered orphaned processing task; retry queued.")
        self._sweep_auto_retryable_blocked_llm_tasks()

        logger.info("Pending task watcher started for %s", self._anima_name)

        while not self._shutdown_event.is_set():
            try:
                # Process command-type pending tasks
                for path in sorted(pending_dir.glob("*.json")):
                    try:
                        task_desc = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        logger.warning(
                            "Invalid JSON in pending task file: %s",
                            path.name,
                        )
                        path.unlink(missing_ok=True)
                        continue

                    try:
                        processing_path = cmd_processing_dir / path.name
                        path.rename(processing_path)
                    except OSError:
                        logger.exception(
                            "Failed to move task to processing: %s",
                            path.name,
                        )
                        continue

                    claimed_task_id = self._claim_processing_task(
                        processing_path,
                        cmd_failed_dir,
                        task_desc,
                    )
                    if claimed_task_id is None:
                        continue
                    claim_transferred = False
                    try:
                        logger.info(
                            "Picked up pending task: id=%s tool=%s subcmd=%s anima=%s",
                            task_desc.get("task_id", "?"),
                            task_desc.get("tool_name", "?"),
                            task_desc.get("subcommand", ""),
                            self._anima_name,
                        )
                        background_task = await self.execute_pending_task(task_desc)
                        if isinstance(background_task, asyncio.Task):
                            self._track_command_claim(
                                background_task,
                                task_id=claimed_task_id,
                                processing_path=processing_path,
                                failed_dir=cmd_failed_dir,
                            )
                            claim_transferred = True
                        else:
                            _unlink_processing_descriptor(processing_path)
                    except Exception:
                        logger.exception(
                            "Error processing pending task file: %s",
                            path.name,
                        )
                        try:
                            processing_path.rename(cmd_failed_dir / path.name)
                        except OSError:
                            logger.exception(
                                "Failed to move task to failed: %s",
                                path.name,
                            )
                    finally:
                        if not claim_transferred:
                            self._active_task_ids.discard(claimed_task_id)
                            _remove_processing_lease(processing_path)

                # Scan LLM pending tasks — group batch tasks, execute serial ones
                self._restore_deferred_tasks(
                    llm_deferred_dir,
                    llm_pending_dir,
                    llm_suppressed_dir,
                    llm_failed_dir,
                )

                for path in sorted(llm_pending_dir.glob("*.json")):
                    try:
                        task_desc = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        logger.warning(
                            "Invalid JSON in LLM pending task file: %s",
                            path.name,
                        )
                        path.unlink(missing_ok=True)
                        continue

                    if not self._handle_llm_attention_gate(
                        path,
                        task_desc,
                        deferred_dir=llm_deferred_dir,
                        suppressed_dir=llm_suppressed_dir,
                        failed_dir=llm_failed_dir,
                    ):
                        continue

                    try:
                        processing_path = llm_processing_dir / path.name
                        path.rename(processing_path)
                    except OSError:
                        logger.exception(
                            "Failed to move LLM task to processing: %s",
                            path.name,
                        )
                        continue

                    claimed_task_id = self._claim_processing_task(
                        processing_path,
                        llm_failed_dir,
                        task_desc,
                    )
                    if claimed_task_id is None:
                        continue
                    claim_transferred = False
                    try:
                        batch_id = task_desc.get("batch_id")
                        if batch_id:
                            self._batch_tasks.setdefault(batch_id, []).append(task_desc)
                            claim_transferred = True
                            logger.info(
                                "Queued batch task: id=%s batch=%s anima=%s",
                                task_desc.get("task_id", "?"),
                                batch_id,
                                self._anima_name,
                            )
                        else:
                            task_id = task_desc.get("task_id", "")
                            logger.info(
                                "Picked up LLM pending task: id=%s anima=%s",
                                task_id,
                                self._anima_name,
                            )
                            if self._worker_pool_size() > 1:
                                worker_slot = await self._acquire_worker(task_id)
                                if worker_slot is not None:
                                    dispatch = asyncio.create_task(
                                        self._execute_claimed_llm_task(
                                            task_desc,
                                            processing_path,
                                            llm_failed_dir,
                                            worker_slot,
                                        ),
                                        name=f"taskexec-{self._anima_name}-{task_id}",
                                    )
                                    self._track_dispatch_task(dispatch)
                                    claim_transferred = True
                                else:
                                    await self._execute_claimed_llm_task(
                                        task_desc,
                                        processing_path,
                                        llm_failed_dir,
                                        None,
                                    )
                                    claim_transferred = True
                            else:
                                await self._execute_claimed_llm_task(
                                    task_desc,
                                    processing_path,
                                    llm_failed_dir,
                                    None,
                                )
                                claim_transferred = True
                        if batch_id:
                            _unlink_processing_descriptor(processing_path)
                    except Exception:
                        logger.exception(
                            "Error processing LLM pending task file: %s",
                            path.name,
                        )
                        try:
                            processing_path.rename(llm_failed_dir / path.name)
                        except OSError:
                            logger.exception(
                                "Failed to move LLM task to failed: %s",
                                path.name,
                            )
                    finally:
                        if not claim_transferred:
                            self._active_task_ids.discard(claimed_task_id)
                            _remove_processing_lease(processing_path)

                # Dispatch accumulated batch tasks
                for batch_id, tasks in list(self._batch_tasks.items()):
                    del self._batch_tasks[batch_id]
                    dispatch = asyncio.create_task(
                        self._execute_claimed_batch(batch_id, tasks),
                        name=f"taskexec-batch-{self._anima_name}-{batch_id}",
                    )
                    self._track_dispatch_task(dispatch)

                # Urgent mode shortens the poll interval so newly-submitted
                # urgent tasks are picked up with minimal latency instead of
                # waiting the full 3 seconds.
                poll_timeout = _PENDING_WATCHER_POLL_INTERVAL
                try:
                    from core.urgent import is_urgent_active

                    if is_urgent_active(self._anima_dir):
                        poll_timeout = 0.2
                except Exception:  # noqa: BLE001
                    pass
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=poll_timeout,
                    )
                    self._wake_event.clear()
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Error in pending task watcher for %s",
                    self._anima_name,
                )
                await asyncio.sleep(_PENDING_WATCHER_POLL_INTERVAL)

        if self._active_dispatch_tasks:
            for task in self._active_dispatch_tasks:
                task.cancel()
            await asyncio.gather(*self._active_dispatch_tasks, return_exceptions=True)
            self._active_dispatch_tasks.clear()
        for tasks in self._batch_tasks.values():
            self._active_task_ids.difference_update(str(task.get("task_id") or "").strip() for task in tasks)
        self._batch_tasks.clear()
        logger.info("Pending task watcher stopped for %s", self._anima_name)

    # ── DAG batch dispatch ──────────────────────────────────────

    async def _dispatch_batch(
        self,
        batch_id: str,
        tasks: list[dict[str, Any]],
    ) -> None:
        """Dispatch a batch of tasks respecting DAG dependencies.

        Independent parallel tasks run under ``_task_semaphore``.
        Serial tasks (``parallel=false``) and dependency-gated tasks
        run sequentially under ``_background_lock``.
        """
        logger.info(
            "[%s] Dispatching batch %s with %d tasks",
            self._anima_name,
            batch_id,
            len(tasks),
        )

        try:
            order = _topological_sort(tasks)
        except ValueError:
            logger.error(
                "[%s] Cycle detected in batch %s; aborting all tasks",
                self._anima_name,
                batch_id,
            )
            for td in tasks:
                self._write_failed_result(td["task_id"], "cycle_in_batch")
                self._sync_task_queue(td["task_id"], "failed", summary="FAILED: cycle_in_batch")
            return

        completed: dict[str, str] = {}  # task_id -> result_summary
        failed: set[str] = set()
        attention_suppressed: set[str] = set()
        remaining = list(order)
        task_ids_in_batch = {td["task_id"] for td in order}

        for td in list(remaining):
            decision = self._attention_decision_for_task_desc(td)
            if decision.executable:
                continue
            task_id = td["task_id"]
            remaining.remove(td)
            failed.add(task_id)
            if decision.reason == "snoozed":
                self._write_deferred_task_json(td)
                self._sync_task_queue(task_id, "pending", summary="snoozed by TaskBoard")
                logger.info(
                    "[%s] Deferred snoozed batch task before dispatch: id=%s",
                    self._anima_name,
                    task_id,
                )
                continue
            attention_suppressed.add(task_id)
            self._cancel_queue_for_attention(task_id, decision.reason)
            self._save_task_result(task_id, _SENTINEL_CANCELLED)
            logger.info(
                "[%s] Suppressed batch task before dispatch: id=%s reason=%s",
                self._anima_name,
                task_id,
                decision.reason,
            )

        for td in order:
            for dep in td.get("depends_on", []):
                if dep in task_ids_in_batch or dep in failed:
                    continue
                decision = self._attention_decision_for_task_desc({"task_id": dep})
                if not decision.executable:
                    failed.add(dep)
                    if decision.reason != "snoozed":
                        attention_suppressed.add(dep)
                        self._cancel_queue_for_attention(dep, decision.reason)

        while remaining:
            ready = [td for td in remaining if _deps_satisfied(td, completed, failed)]
            if not ready:
                for td in remaining:
                    reason = _dependency_failure_reason(td, attention_suppressed)
                    failed.add(td["task_id"])
                    self._write_failed_result(td["task_id"], reason)
                    self._sync_task_queue(td["task_id"], "failed", summary=f"FAILED: {reason}")
                break

            parallel_ready = [td for td in ready if td.get("parallel")]
            serial_ready = [td for td in ready if not td.get("parallel")]

            # Skip parallel tasks whose dependencies have failed (mirror of serial check at 461)
            for td in list(parallel_ready):
                if any(dep in failed for dep in td.get("depends_on", [])):
                    reason = _dependency_failure_reason(td, attention_suppressed)
                    parallel_ready.remove(td)
                    remaining.remove(td)
                    failed.add(td["task_id"])
                    self._write_failed_result(td["task_id"], reason)
                    self._sync_task_queue(td["task_id"], "failed", summary=f"FAILED: {reason}")

            # Execute parallel tasks concurrently under semaphore
            if parallel_ready:
                coros = [self._execute_parallel_task(td, completed, batch_id) for td in parallel_ready]
                results = await asyncio.gather(*coros, return_exceptions=True)
                for task, result in zip(parallel_ready, results, strict=False):
                    remaining.remove(task)
                    if isinstance(result, Exception):
                        logger.error(
                            "[%s] Parallel task %s failed: %s",
                            self._anima_name,
                            task["task_id"],
                            result,
                        )
                        failed.add(task["task_id"])
                        self._write_failed_result(task["task_id"], str(result))
                        self._sync_task_queue(
                            task["task_id"],
                            "failed",
                            summary=f"FAILED: {str(result)[:200]}",
                        )
                        reply_to = task.get("reply_to")
                        if isinstance(reply_to, dict):
                            reply_to = reply_to.get("name")
                        elif not isinstance(reply_to, str):
                            reply_to = None
                        if reply_to:
                            try:
                                from core.execution._sanitize import ORIGIN_ANIMA
                                from core.i18n import t

                                notify_text = t(
                                    "pending_executor.task_fail_notify",
                                    task_id=task["task_id"],
                                    title=task.get("description", "unknown"),
                                    error=f"Batch execution failed: {type(result).__name__}: {str(result)[:200]}",
                                )
                                for _attempt in range(2):
                                    try:
                                        self._anima.messenger.send(
                                            to=reply_to,
                                            content=notify_text,
                                            origin_chain=[ORIGIN_ANIMA],
                                        )
                                        break
                                    except Exception:
                                        if _attempt > 0:
                                            logger.error(
                                                "[%s] Batch failure notification failed after retry to %s",
                                                self._anima_name,
                                                reply_to,
                                                exc_info=True,
                                            )
                            except Exception:
                                logger.warning("[%s] Failed to build batch failure notification", self._anima_name)
                    elif result == _SENTINEL_DEFERRED:
                        failed.add(task["task_id"])
                    elif task.get("_attention_suppressed_reason"):
                        failed.add(task["task_id"])
                        attention_suppressed.add(task["task_id"])
                    else:
                        completed[task["task_id"]] = result or ""

            # Execute serial tasks sequentially
            for task in serial_ready:
                remaining.remove(task)
                if any(dep in failed for dep in task.get("depends_on", [])):
                    reason = _dependency_failure_reason(task, attention_suppressed)
                    failed.add(task["task_id"])
                    self._write_failed_result(task["task_id"], reason)
                    self._sync_task_queue(task["task_id"], "failed", summary=f"FAILED: {reason}")
                    continue
                try:
                    result = await self._execute_serial_batch_task(
                        task,
                        completed,
                        batch_id,
                    )
                    if result == _SENTINEL_DEFERRED:
                        failed.add(task["task_id"])
                    elif task.get("_attention_suppressed_reason"):
                        failed.add(task["task_id"])
                        attention_suppressed.add(task["task_id"])
                    else:
                        completed[task["task_id"]] = result or ""
                except Exception as exc:
                    logger.error(
                        "[%s] Serial batch task %s failed: %s",
                        self._anima_name,
                        task["task_id"],
                        exc,
                    )
                    failed.add(task["task_id"])
                    self._write_failed_result(task["task_id"], str(exc))
                    self._sync_task_queue(
                        task["task_id"],
                        "failed",
                        summary=f"FAILED: {str(exc)[:200]}",
                    )
                    reply_to = task.get("reply_to")
                    if isinstance(reply_to, dict):
                        reply_to = reply_to.get("name")
                    elif not isinstance(reply_to, str):
                        reply_to = None
                    if reply_to:
                        try:
                            from core.execution._sanitize import ORIGIN_ANIMA
                            from core.i18n import t

                            notify_text = t(
                                "pending_executor.task_fail_notify",
                                task_id=task["task_id"],
                                title=task.get("description", "unknown"),
                                error=f"Batch execution failed: {type(exc).__name__}: {str(exc)[:200]}",
                            )
                            for _attempt in range(2):
                                try:
                                    self._anima.messenger.send(
                                        to=reply_to,
                                        content=notify_text,
                                        origin_chain=[ORIGIN_ANIMA],
                                    )
                                    break
                                except Exception:
                                    if _attempt > 0:
                                        logger.error(
                                            "[%s] Batch failure notification failed after retry to %s",
                                            self._anima_name,
                                            reply_to,
                                            exc_info=True,
                                        )
                        except Exception:
                            logger.warning("[%s] Failed to build batch failure notification", self._anima_name)

        logger.info(
            "[%s] Batch %s complete: %d succeeded, %d failed",
            self._anima_name,
            batch_id,
            len(completed),
            len(failed),
        )

    async def _execute_parallel_task(
        self,
        task_desc: dict[str, Any],
        completed_results: dict[str, str],
        batch_id: str,
    ) -> str:
        """Execute a single parallel task under the semaphore (no _background_lock)."""
        task_id = task_desc.get("task_id", "unknown")
        title = task_desc.get("title", "Untitled")

        async with self._get_semaphore():
            # Register in active parallel tasks
            self._anima._active_parallel_tasks[task_id] = {
                "title": title,
                "description": (task_desc.get("description", ""))[:100],
                "started_at": datetime.now(UTC).isoformat(),
                "batch_id": batch_id,
                "status": "running",
                "depends_on": task_desc.get("depends_on", []),
            }
            try:
                result = await self._run_task_in_worker(task_desc, completed_results)
                self._save_task_result(task_id, result)
                status, summary = _classify_task_result_for_desc(result, task_desc)
                self._sync_task_queue(task_id, status, summary=summary)
                if status == "done":
                    await self._handle_goal_completion(task_desc, result)
                return result
            finally:
                self._anima._active_parallel_tasks.pop(task_id, None)

    async def _execute_serial_batch_task(
        self,
        task_desc: dict[str, Any],
        completed_results: dict[str, str],
        batch_id: str,
    ) -> str:
        """Execute a serial batch task under _background_lock."""
        task_id = task_desc.get("task_id", "unknown")
        result = await self._run_task_in_worker(task_desc, completed_results)
        self._save_task_result(task_id, result)
        status, summary = _classify_task_result_for_desc(result, task_desc)
        self._sync_task_queue(task_id, status, summary=summary)
        if status == "done":
            await self._handle_goal_completion(task_desc, result)
        return result

    async def _run_task_in_worker(
        self,
        task_desc: dict[str, Any],
        completed_results: dict[str, str] | None = None,
        *,
        worker_slot: BackgroundWorkerSlot | None = None,
    ) -> str:
        """Run one LLM task with workspace exclusion and a worker lease."""
        task_id = task_desc.get("task_id", "unknown")
        workspace_lock = self._workspace_lock(task_desc)
        async with workspace_lock if workspace_lock is not None else contextlib.nullcontext():
            leased_here = worker_slot is None
            slot = worker_slot or await self._acquire_worker(task_id)
            try:
                return await self._run_llm_task(
                    task_desc,
                    completed_results,
                    worker_slot=slot,
                )
            finally:
                if leased_here:
                    await self._release_worker(slot)

    async def _run_llm_task(
        self,
        task_desc: dict[str, Any],
        completed_results: dict[str, str] | None = None,
        *,
        worker_slot: BackgroundWorkerSlot | None = None,
    ) -> str:
        """Run an LLM task and record its complete activity lifecycle."""
        from core.memory.activity import ActivityLogger

        task_id, title, _description = _task_activity_identity(task_desc)
        submitted_by = str(task_desc.get("submitted_by") or "unknown")
        trigger = f"task:{task_id}"
        task_meta = {
            "task_id": task_id,
            "title": title,
            "submitted_by": submitted_by,
        }
        activity = ActivityLogger(self._anima_dir)
        activity.log(
            "task_exec_start",
            summary=t("pending_executor.task_exec_start", title=title),
            ctx=trigger,
            meta=task_meta,
        )

        try:
            result = await self._run_llm_task_under_agent_session_context(
                task_desc,
                completed_results,
                worker_slot=worker_slot,
            )
        except asyncio.CancelledError:
            activity.log(
                "task_exec_end",
                summary=t("pending_executor.task_exec_end", title=title, result="cancelled"),
                ctx=trigger,
                meta={**task_meta, "status": "cancelled"},
                safe=True,
            )
            raise
        except Exception as exc:
            error = str(exc).strip()[:200] or type(exc).__name__
            activity.log(
                "task_exec_end",
                summary=t("pending_executor.task_exec_end", title=title, result=error),
                ctx=trigger,
                meta={
                    **task_meta,
                    "status": "failed",
                    "error": error,
                    "error_type": type(exc).__name__,
                },
                safe=True,
            )
            raise

        status = {
            _SENTINEL_CANCELLED: "cancelled",
            _SENTINEL_EXPIRED: "expired",
            _SENTINEL_DEFERRED: "deferred",
        }.get(result, "completed")
        activity.log(
            "task_exec_end",
            summary=t("pending_executor.task_exec_end", title=title, result=result[:200]),
            ctx=trigger,
            meta={**task_meta, "status": status, "result": result[:200]},
        )
        return result

    async def _run_llm_task_under_agent_session_context(
        self,
        task_desc: dict[str, Any],
        completed_results: dict[str, str] | None = None,
        *,
        worker_slot: BackgroundWorkerSlot | None = None,
    ) -> str:
        """Core LLM task execution logic shared by parallel and serial paths.

        Returns the result summary string.
        """
        task_id, title, description = _task_activity_identity(task_desc)
        context = task_desc.get("context", "")
        acceptance_criteria = task_desc.get("acceptance_criteria", [])
        constraints = task_desc.get("constraints", [])
        file_paths = task_desc.get("file_paths", [])
        reply_to = task_desc.get("reply_to")
        submitted_by = task_desc.get("submitted_by", "unknown")
        submitted_at = task_desc.get("submitted_at", "")

        # Skip if task was cancelled in task_queue (batch path; single path checks in watcher)
        try:
            from core.memory.task_queue import TaskQueueManager

            entry = TaskQueueManager(self._anima_dir).get_task_by_id(task_id)
            if entry and entry.status == "cancelled":
                logger.info(
                    "[%s] Skipping cancelled LLM task: id=%s",
                    self._anima_name,
                    task_id,
                )
                return _SENTINEL_CANCELLED
        except Exception:
            logger.debug(
                "Could not check task_queue for cancellation: %s",
                task_id,
                exc_info=True,
            )

        decision = self._attention_decision_for_task_desc(task_desc)
        if not decision.executable:
            if decision.reason == "snoozed":
                self._write_deferred_task_json(task_desc)
                logger.info(
                    "[%s] Deferring snoozed LLM task at final defense: id=%s",
                    self._anima_name,
                    task_id,
                )
                return _SENTINEL_DEFERRED
            task_desc["_attention_suppressed_reason"] = decision.reason
            self._cancel_queue_for_attention(task_id, decision.reason)
            logger.info(
                "[%s] Skipping non-executable LLM task: id=%s reason=%s",
                self._anima_name,
                task_id,
                decision.reason,
            )
            return _SENTINEL_CANCELLED

        # TTL check
        if submitted_at:
            try:
                sub_dt = datetime.fromisoformat(submitted_at)
                if sub_dt.tzinfo is None:
                    sub_dt = sub_dt.replace(tzinfo=UTC)
                now_utc = datetime.now(UTC)
                age_hours = (now_utc - sub_dt).total_seconds() / 3600
                if age_hours > _LLM_TASK_TTL_HOURS:
                    logger.warning(
                        "[%s] Skipping expired LLM task: %s (age=%.1fh, TTL=%dh)",
                        self._anima_name,
                        task_id,
                        age_hours,
                        _LLM_TASK_TTL_HOURS,
                    )
                    return _SENTINEL_EXPIRED
            except (ValueError, TypeError):
                pass

        # Build dependency context for batch tasks
        dep_context = ""
        if completed_results:
            dep_context = self._build_dependency_context(task_desc, completed_results)

        from core.memory.streaming_journal import StreamingJournal
        from core.paths import load_prompt

        trigger = f"task:{task_id}"

        _none = t("pending_executor.none_value")
        criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria) if acceptance_criteria else _none
        constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else _none
        paths_text = "\n".join(f"- {p}" for p in file_paths) if file_paths else _none

        full_context = context or _none
        if dep_context:
            full_context = f"{full_context}\n\n{dep_context}"

        working_directory = task_desc.get("working_directory", "")
        if not working_directory:
            working_directory = _resolve_default_workspace(self._anima_dir)
        prompt = load_prompt(
            "task_exec",
            task_id=task_id,
            title=title,
            submitted_by=submitted_by,
            workspace=working_directory or t("pending_executor.workspace_not_specified"),
            description=description,
            context=full_context,
            acceptance_criteria=criteria_text,
            constraints=constraints_text,
            file_paths=paths_text,
            active_workers=self._format_active_sibling_tasks(task_id) or _none,
        )

        lane_getter = getattr(type(self._anima), "_agent_for_lane", None)
        if worker_slot is not None:
            agent = worker_slot.agent
        else:
            agent = self._anima._agent_for_lane("background") if callable(lane_getter) else self._anima.agent
        bg_config = None
        bg_config_getter = getattr(type(self._anima), "_resolve_background_config", None)
        if callable(bg_config_getter):
            try:
                bg_config = self._anima._resolve_background_config()
            except Exception:
                logger.debug("[%s] Failed to resolve background model for TaskExec", self._anima_name, exc_info=True)

        task_model_name = getattr(bg_config, "model", None) or getattr(agent.model_config, "model", "")
        try:
            from core.task_granularity import assess_task_granularity

            decision = assess_task_granularity(
                model_name=task_model_name,
                title=title,
                description=description,
                context=context,
                allow_multistage=bool(task_desc.get("allow_multistage")),
            )
        except Exception:
            logger.debug("[%s] Task granularity check skipped for %s", self._anima_name, task_id, exc_info=True)
        else:
            if not decision.allowed:
                raise TaskExecError(
                    f"{decision.reason}: {decision.guidance} "
                    f"model={decision.model_name}; capability={decision.capability}; task_id={task_id}"
                )

        original_config = None
        if bg_config is not None:
            original_config = agent.model_config
            agent.update_model_config(bg_config)

        if "machine" in description.lower():
            prompt += "\n\n" + t("pending_executor.machine_directive")

        journal = StreamingJournal(self._anima_dir, session_type="task", thread_id=task_id)
        journal.open(trigger=trigger)

        accumulated_text = ""
        result_summary = ""
        task_failed_reason = ""
        had_error = False
        error_message = ""

        # Urgent-mode activation (Phase C-3): if this task is flagged urgent
        # (by Inbox prefix detection, delegate_task cascade, or CLI
        # urgent-submit), register the task_id in urgent_active.json so rate
        # limits / cooldowns / scheduler throttling are bypassed for the
        # duration.  Remove on completion / failure.
        _urgent_task = task_desc.get("priority") == "urgent"
        _urgent_registered = False
        if _urgent_task:
            try:
                from core.urgent import add_urgent

                add_urgent(
                    self._anima_dir,
                    task_id,
                    note=f"task:{title[:80]} from {submitted_by}",
                )
                _urgent_registered = True
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[%s] urgent registration failed for task %s",
                    self._anima_name,
                    task_id,
                    exc_info=True,
                )

        try:
            if worker_slot is not None:
                session_context = worker_slot.session_lock
            elif callable(getattr(type(self._anima), "_agent_session_context", None)):
                session_context = self._anima._agent_session_context("background")
            else:
                session_context = getattr(self._anima, "_agent_session_lock", None)
                if not isinstance(session_context, asyncio.Lock):
                    session_context = None
            if session_context is None:
                from contextlib import nullcontext

                session_context = nullcontext()
            async with session_context:
                if worker_slot is not None:
                    interrupt_event = worker_slot.interrupt_event
                    self._anima._interrupt_events[task_id] = interrupt_event
                elif self._anima and hasattr(self._anima, "_get_interrupt_event"):
                    interrupt_event = self._anima._get_interrupt_event("_background")
                else:
                    interrupt_event = None
                if interrupt_event is not None:
                    interrupt_event.clear()
                    agent.set_interrupt_event(interrupt_event)
                if working_directory:
                    agent.set_task_cwd(Path(working_directory))
                try:
                    agent.reset_reply_tracking(session_type="task")
                    agent.reset_read_paths()
                    async for chunk in agent.run_cycle_streaming(
                        prompt,
                        trigger=trigger,
                        thread_id=task_id,
                    ):
                        chunk_type = chunk.get("type")
                        if chunk_type == "text_delta":
                            accumulated_text += chunk.get("text", "")
                            journal.write_text(chunk.get("text", ""))
                        elif chunk_type == "error":
                            had_error = True
                            error_message = chunk.get("message", "unknown error")
                            if _is_provider_rate_limit_error(error_message):
                                logger.warning(
                                    "[%s] Provider rate limit during task %s: %s",
                                    self._anima_name,
                                    task_id,
                                    error_message,
                                )
                            else:
                                logger.warning(
                                    "[%s] Streaming error during task %s: %s",
                                    self._anima_name,
                                    task_id,
                                    error_message,
                                )
                        elif chunk_type == "retry_start":
                            had_error = False
                            error_message = ""
                        elif chunk_type == "cycle_done":
                            cycle_result = chunk.get("cycle_result", {})
                            # Prefer LLM-provided summary; fall back to full accumulated_text
                            # (we intentionally preserve the entire text so downstream
                            # notifications and board mirrors never truncate content).
                            result_summary = cycle_result.get(
                                "summary",
                                accumulated_text,
                            )
                            if cycle_result.get("action") == "error":
                                task_failed_reason = result_summary or "task execution failed"
                            journal.finalize(summary=result_summary[:500])
                finally:
                    agent.set_task_cwd(None)
                    if original_config is not None:
                        agent.update_model_config(original_config)
                    if worker_slot is not None and self._anima._interrupt_events.get(task_id) is interrupt_event:
                        self._anima._interrupt_events.pop(task_id, None)
        finally:
            journal.close()
            if _urgent_registered:
                try:
                    from core.urgent import remove_urgent

                    remove_urgent(self._anima_dir, task_id)
                except Exception:  # noqa: BLE001
                    logger.debug("urgent removal failed for %s", task_id, exc_info=True)

        if had_error:
            _queue_done = False
            try:
                from core.memory.task_queue import TaskQueueManager

                _entry = TaskQueueManager(self._anima_dir).get_task_by_id(task_id)
                if _entry and _entry.status == "done":
                    _queue_done = True
                    logger.info(
                        "[%s] Task %s stream error suppressed: already marked done in queue",
                        self._anima_name,
                        task_id,
                    )
                    if not result_summary:
                        result_summary = (
                            _entry.summary or accumulated_text[:500] or t("pending_executor.task_completed")
                        )
            except Exception as e:
                logger.debug("pending_executor: failed to check task queue for task %s: %s", task_id, e)

            if not _queue_done:
                if _is_provider_rate_limit_error(error_message):
                    deferred_desc = dict(task_desc)
                    provider_cooldown_until = _provider_cooldown_until_from_message(error_message)
                    deferred_desc["_provider_rate_limit_error"] = error_message
                    deferred_desc["_provider_cooldown_until"] = provider_cooldown_until.isoformat()
                    self._write_deferred_task_json(deferred_desc)
                    logger.warning(
                        "[%s] Deferred provider-rate-limited task %s until %s",
                        self._anima_name,
                        task_id,
                        provider_cooldown_until.isoformat(),
                    )
                    return _SENTINEL_PROVIDER_RATE_LIMIT
                raise TaskExecError(f"Task {task_id} encountered streaming error: {error_message}")
        if task_failed_reason:
            raise RuntimeError(task_failed_reason)

        if not result_summary:
            result_summary = accumulated_text or t("pending_executor.task_completed")

        auth_failure = _detect_task_auth_failure(result_summary or accumulated_text)
        if auth_failure:
            raise TaskExecError(auth_failure)

        # Send completion notification
        if reply_to:
            if isinstance(reply_to, dict):
                reply_to = reply_to.get("name")
            elif not isinstance(reply_to, str):
                reply_to = None
        # Skip self-notifications: when an Anima submits a task for itself,
        # a completion DM back to self is pure noise and the body often
        # carries human-directed content that gets misrouted.
        if reply_to and reply_to == self._anima_name:
            logger.info(
                "[%s] Skipping self-directed completion notification for task %s",
                self._anima_name,
                task_id,
            )
            reply_to = None

        # Skip notification when the result carries no information: the
        # completion is already tracked in the task queue / activity log,
        # and an empty echo only costs the recipient a full LLM cycle.
        if reply_to:
            _summary_body = (result_summary or "").strip()
            if (
                not _summary_body
                or _summary_body == t("pending_executor.task_completed")
                or _summary_body.startswith("[Session interrupted")
            ):
                logger.info(
                    "[%s] Skipping empty task completion notification for %s (task %s)",
                    self._anima_name,
                    reply_to,
                    task_id,
                )
                reply_to = None
        if reply_to:
            try:
                notify_text = load_prompt(
                    "task_complete_notify",
                    task_id=task_id,
                    title=title,
                    result_summary=result_summary[:_TASK_COMPLETE_NOTIFY_MAX_CHARS],
                )
                from core.execution._sanitize import ORIGIN_ANIMA

                for _attempt in range(2):
                    try:
                        self._anima.messenger.send(
                            to=reply_to,
                            content=notify_text,
                            origin_chain=[ORIGIN_ANIMA],
                            meta={
                                "notification_type": "task_completion",
                                "completed_task_id": task_id,
                            },
                        )
                        break
                    except Exception:
                        if _attempt == 0:
                            logger.warning(
                                "[%s] Task completion notification failed, retrying",
                                self._anima_name,
                            )
                        else:
                            logger.error(
                                "[%s] Task completion notification failed after retry to %s",
                                self._anima_name,
                                reply_to,
                                exc_info=True,
                            )
                            if hasattr(self._anima, "_activity"):
                                self._anima._activity.log(
                                    "error",
                                    content=f"Task completion notification failed: {task_id} → {reply_to}",
                                )
            except Exception:
                logger.warning(
                    "[%s] Failed to build task completion notification",
                    self._anima_name,
                    exc_info=True,
                )

        logger.info("[%s] LLM task completed: id=%s", self._anima_name, task_id)
        return result_summary

    def wake(self) -> None:
        """Signal the watcher to check for new tasks immediately."""
        self._wake_event.set()

    async def execute_pending_task(
        self,
        task_desc: dict[str, Any],
        *,
        worker_slot: BackgroundWorkerSlot | None = None,
    ) -> asyncio.Task[None] | None:
        """Execute a pending task via BackgroundTaskManager or LLM.

        Routes by task_type: 'llm' → _execute_llm_task, else command subprocess.
        """
        task_type = task_desc.get("task_type", "command")

        if task_type == "llm":
            await self._execute_llm_task(task_desc, worker_slot=worker_slot)
            return None

        if not self._anima:
            logger.warning("Cannot execute pending task: anima not initialized")
            return

        lane_getter = getattr(type(self._anima), "_agent_for_lane", None)
        agent = self._anima._agent_for_lane("background") if callable(lane_getter) else self._anima.agent
        bg_mgr = agent.background_manager
        if not bg_mgr:
            logger.warning(
                "Cannot execute pending task: BackgroundTaskManager not available",
            )
            return

        tool_name = task_desc.get("tool_name", "")
        subcommand = task_desc.get("subcommand", "")
        raw_args = task_desc.get("raw_args", [])
        anima_dir = task_desc.get("anima_dir", str(self._anima_dir))

        # Build tool args dict for ExternalToolDispatcher
        tool_args = {
            "subcommand": subcommand,
            "raw_args": raw_args,
            "anima_dir": anima_dir,
        }

        task_id = task_desc.get("task_id", "")
        queue_link = _command_queue_link(task_id, tool_name, subcommand)
        if queue_link is not None:
            queue_task_id, success_status, failure_status = queue_link
            tool_args.update(
                {
                    "queue_task_id": queue_task_id,
                    "queue_success_status": success_status,
                    "queue_failure_status": failure_status,
                }
            )
            self._sync_task_queue(
                queue_task_id,
                "in_progress",
                summary=f"started command: {tool_name} {subcommand}".strip(),
            )

        logger.info(
            "Submitting pending task to BackgroundTaskManager: id=%s tool=%s subcmd=%s",
            task_id,
            tool_name,
            subcommand,
        )

        def _dispatch_fn(name: str, args: dict[str, Any]) -> str:
            """Execute the tool via CLI subprocess (same as direct execution)."""
            import os
            import shutil
            import subprocess
            import sys
            from pathlib import Path

            # name may be composite (e.g. "transcribe:audio"); extract module name
            module_name = name.split(":")[0] if ":" in name else name
            project_root = Path(__file__).resolve().parents[2]
            scripts_dir = project_root / ".venv" / "Scripts"
            executable_name = "animaworks-tool.exe" if os.name == "nt" else "animaworks-tool"
            tool_exe = scripts_dir / executable_name if (scripts_dir / executable_name).exists() else None
            tool_cmd = str(tool_exe) if tool_exe else (shutil.which("animaworks-tool") or "animaworks-tool")
            cmd = [tool_cmd, module_name]
            subcmd = args.get("subcommand", "")
            if subcmd:
                cmd.append(subcmd)
            cmd.extend(args.get("raw_args", []))
            # Remove subcommand from raw_args if it's already the first element
            if subcmd and args.get("raw_args") and args["raw_args"][0] == subcmd:
                cmd = [tool_cmd, module_name] + args["raw_args"]
            cmd.append("-j")

            env = {
                **os.environ,
                "ANIMAWORKS_ANIMA_DIR": args.get("anima_dir", ""),
            }
            if scripts_dir.exists():
                env["PATH"] = f"{scripts_dir}{os.pathsep}{env.get('PATH', '')}"
            # ANIMAWORKS_EMBED_URL and ANIMAWORKS_VECTOR_URL are inherited from runner env
            # (set by ProcessHandle.child_env_urls) and passed through via **os.environ

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=_PENDING_TASK_SUBPROCESS_TIMEOUT,
                    env=env,
                )
            except FileNotFoundError:
                # Last-resort fallback: run the dispatcher through this Python.
                fallback_cmd = [
                    sys.executable,
                    "-c",
                    "from core.tools import cli_dispatch; cli_dispatch()",
                    module_name,
                    *cmd[2:],
                ]
                result = subprocess.run(
                    fallback_cmd,
                    capture_output=True,
                    text=True,
                    timeout=_PENDING_TASK_SUBPROCESS_TIMEOUT,
                    env=env,
                    cwd=str(project_root),
                )
            if result.returncode != 0:
                error_msg = result.stderr.strip() or f"Exit code {result.returncode}"
                raise ToolExecutionError(f"Tool {name} failed: {error_msg}")
            stdout = result.stdout.strip()
            try:
                payload = json.loads(stdout) if stdout else {}
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict) and payload.get("ok") is False:
                error_msg = payload.get("error") or payload.get("message") or stdout[:500]
                raise ToolExecutionError(f"Tool {name} reported ok=false: {error_msg}")
            return stdout

        # Submit to BackgroundTaskManager
        composite_name = f"{tool_name}:{subcommand}" if subcommand else tool_name
        background_task_id = bg_mgr.submit(composite_name, tool_args, _dispatch_fn)
        if queue_link is not None:
            try:
                from core.memory.task_queue import TaskQueueManager

                TaskQueueManager(self._anima_dir).update_meta(
                    queue_link[0],
                    {
                        "background_task_id": background_task_id,
                        "background_tool": composite_name,
                    },
                )
            except Exception:
                logger.debug(
                    "[%s] Failed to attach background task metadata: queue=%s bg=%s",
                    self._anima_name,
                    queue_link[0],
                    background_task_id,
                    exc_info=True,
                )
        active_tasks = getattr(bg_mgr, "_async_tasks", None)
        if isinstance(active_tasks, dict):
            background_task = active_tasks.get(background_task_id)
            if isinstance(background_task, asyncio.Task):
                return background_task
        return None

    async def _execute_llm_task(
        self,
        task_desc: dict[str, Any],
        *,
        worker_slot: BackgroundWorkerSlot | None = None,
    ) -> None:
        """Execute an LLM task in an isolated background worker.

        The task is executed as a minimal-context LLM session using
        the task_exec.md template.  Delegates to ``_run_llm_task``
        for the actual execution logic.
        """
        task_id = task_desc.get("task_id", "unknown")

        logger.info(
            "[%s] Executing LLM task: id=%s title=%s",
            self._anima_name,
            task_id,
            task_desc.get("title", ""),
        )

        preleased = worker_slot is not None
        keepalive_task: asyncio.Future[Any] | None = None
        try:
            pool_capable = callable(getattr(type(self._anima), "_acquire_background_worker", None))
            if not pool_capable:
                # Compatibility for older DigitalAnima-like integrations and
                # focused test doubles that do not expose the worker pool.
                await self._anima._background_lock.acquire()
                self._anima._mark_busy_start()
            keepalive = getattr(self._anima, "_keepalive_while_busy", None)
            if callable(keepalive):
                keepalive_result = keepalive()
                if inspect.isawaitable(keepalive_result):
                    keepalive_task = asyncio.ensure_future(keepalive_result)
            self._anima._status_slots["background"] = "task_exec"
            self._anima._task_slots["background"] = task_id
            self._sync_task_queue(task_id, "in_progress")
            if pool_capable:
                result = await self._run_task_in_worker(task_desc, worker_slot=worker_slot)
            else:
                result = await self._run_llm_task(task_desc)
            status, summary = _classify_task_result_for_desc(result, task_desc)
            self._sync_task_queue(task_id, status, summary=summary)
            if status == "done":
                await self._handle_goal_completion(task_desc, result)
        except Exception as exc:
            logger.exception(
                "[%s] LLM task failed: id=%s",
                self._anima_name,
                task_id,
            )
            self._anima._status_slots["background"] = "idle"
            self._anima._task_slots["background"] = ""
            if self._auto_requeue_stream_error_llm_task(task_desc, exc):
                return
            self._write_failed_result(
                task_id,
                f"{type(exc).__name__}: {str(exc)[:200]}",
            )
            self._sync_task_queue(
                task_id,
                "failed",
                summary=f"FAILED: {type(exc).__name__}: {str(exc)[:200]}",
            )
            reply_to = task_desc.get("reply_to")
            if isinstance(reply_to, dict):
                reply_to = reply_to.get("name")
            elif not isinstance(reply_to, str):
                reply_to = None
            if reply_to:
                try:
                    from core.execution._sanitize import ORIGIN_ANIMA
                    from core.i18n import t

                    notify_text = t(
                        "pending_executor.task_fail_notify",
                        task_id=task_id,
                        title=task_desc.get("description", "unknown"),
                        error=f"{type(exc).__name__}: {str(exc)[:200]}",
                    )
                    for _attempt in range(2):
                        try:
                            self._anima.messenger.send(
                                to=reply_to,
                                content=notify_text,
                                origin_chain=[ORIGIN_ANIMA],
                            )
                            break
                        except Exception:
                            if _attempt == 0:
                                logger.warning(
                                    "[%s] Task failure notification failed, retrying to %s",
                                    self._anima_name,
                                    reply_to,
                                )
                            else:
                                logger.error(
                                    "[%s] Task failure notification failed after retry to %s",
                                    self._anima_name,
                                    reply_to,
                                    exc_info=True,
                                )
                                if hasattr(self._anima, "_activity"):
                                    self._anima._activity.log(
                                        "error",
                                        content=f"Task failure notification failed: {task_id} → {reply_to}",
                                    )
                except Exception:
                    logger.warning(
                        "[%s] Failed to build task failure notification for %s",
                        self._anima_name,
                        reply_to,
                        exc_info=True,
                    )
        finally:
            if keepalive_task is not None:
                keepalive_task.cancel()
                await asyncio.gather(keepalive_task, return_exceptions=True)
            if preleased:
                await self._release_worker(worker_slot)
            if not callable(getattr(type(self._anima), "_acquire_background_worker", None)):
                if self._anima._background_lock.locked():
                    self._anima._background_lock.release()
            active_workers = getattr(self._anima, "_active_background_workers", {})
            if isinstance(active_workers, dict) and active_workers:
                self._anima._status_slots["background"] = "task_exec"
                self._anima._task_slots["background"] = next(iter(active_workers.values()))
            else:
                self._anima._status_slots["background"] = "idle"
                self._anima._task_slots["background"] = ""
            self._anima._clear_busy_status_sidecar_if_idle()
