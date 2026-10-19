from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Task payload validation, publication, and persistence fallbacks."""

import errno
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Literal

from core.exceptions import TaskOwnedByOther, TaskPersistenceError
from core.schemas import TaskEntry
from core.tasks.queue import TaskQueueManager

logger = logging.getLogger("animaworks.tasks_dispatch")


def _post_tasks(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Retry a lost response with the same IDs, never publish new work IDs."""
    import httpx

    from core.tasks.board.tasks import current_attempt_identity

    payload = {**payload, "attempt_identity": current_attempt_identity()}
    from core.internal_api import host_api

    for attempt in range(2):
        try:
            response = host_api.post(
                f"/api/internal/{endpoint}",
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TransportError:
            if attempt:
                raise
        except httpx.HTTPStatusError as exc:
            if attempt or exc.response.status_code < 500:
                raise
    raise RuntimeError("Unreachable task publication retry state")


def is_task_permission_error(exc: BaseException) -> bool:
    """Proxy denied storage access, never lock contention or malformed SQL."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and current.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
            return True
        if isinstance(current, sqlite3.OperationalError):
            code = getattr(current, "sqlite_errorcode", 0) & 0xFF
            denied = any(
                text in str(current).lower()
                for text in (
                    "readonly",
                    "read-only",
                    "permission denied",
                    "access denied",
                    "operation not permitted",
                )
            )
            if denied and code in {0, sqlite3.SQLITE_READONLY, sqlite3.SQLITE_PERM, sqlite3.SQLITE_CANTOPEN}:
                return True
        current = current.__cause__ or current.__context__
    return False


def update_task(
    manager: TaskQueueManager,
    task_id: str,
    status: str | None,
    *,
    summary: str | None = None,
    result: str | None = None,
    resume: bool = False,
    waiting_for: dict[str, Any] | None = None,
    scope_note: str | None = None,
) -> TaskEntry | None:
    """Update task status, proxying only sandbox storage denial.

    When ``resume`` is True the task is requeued under its original task_id
    using its saved execution input (status must be 'pending'). ``scope_note``
    may be supplied without a status change.
    """
    from core.time_utils import now_iso

    if result is not None:
        summary = result
    meta: dict[str, Any] = {}
    if status == "done":
        meta = {"completed_by": "agent_declaration", "declared_at": now_iso()}
        if summary is not None:
            meta["result_note"] = summary
    try:
        return persist_task_update(
            manager,
            task_id,
            status,
            summary=summary,
            resume=resume,
            meta_patch=meta or None,
            waiting_for=waiting_for,
            scope_note=scope_note,
        )
    except Exception as exc:
        if not is_task_permission_error(exc):
            raise
        try:
            response = _post_tasks(
                "update-task",
                {
                    "anima_name": manager.anima_dir.name,
                    "task_id": task_id,
                    "status": status,
                    "summary": summary,
                    "meta": meta,
                    "resume": resume,
                    "waiting_for": waiting_for,
                    "scope_note": scope_note,
                },
            )
        except Exception as fallback_exc:
            response_obj = getattr(fallback_exc, "response", None)
            if response_obj is not None and response_obj.status_code in {400, 409}:
                try:
                    payload = response_obj.json()
                except Exception:
                    payload = {}
                if payload.get("error_type") == "TaskOwnedByOther":
                    raise TaskOwnedByOther(str(payload.get("owner") or "unknown")) from fallback_exc
                if payload.get("error_type") == "InvalidArguments":
                    raise ValueError(str(payload.get("detail") or "Invalid task update")) from fallback_exc
            raise
        if response.get("ok") is False:
            if response.get("error_type") == "TaskOwnedByOther":
                raise TaskOwnedByOther(str(response.get("owner") or "unknown")) from None
            if response.get("error_type") == "InvalidArguments":
                raise ValueError(str(response.get("detail") or "Invalid task update")) from None
            raise TaskPersistenceError("Task host rejected update-task request") from None
        if response.get("ok") is not True or not isinstance(response.get("task"), dict):
            raise TaskPersistenceError("Unexpected response from task update host") from exc
        return TaskEntry.model_validate(response["task"])


def persist_task_update(
    manager: TaskQueueManager,
    task_id: str,
    status: str | None,
    *,
    summary: str | None = None,
    resume: bool = False,
    meta_patch: dict[str, Any] | None = None,
    waiting_for: dict[str, Any] | None = None,
    scope_note: str | None = None,
) -> TaskEntry | None:
    """Persist a task update locally and send the matching task notices."""
    from core.i18n import t
    from core.tasks.waiting import normalize_waiting_for
    from core.time_utils import now_iso

    actor = manager.anima_dir.name
    if status is None and scope_note is None:
        raise ValueError("status is required unless scope_note is provided")
    normalized_wait: dict[str, str] | None = None
    if waiting_for is not None:
        normalized_wait = normalize_waiting_for(waiting_for, status)
    note: str | None = None
    if scope_note is not None:
        if not isinstance(scope_note, str) or not scope_note.strip():
            raise ValueError("scope_note must be a non-empty string")
        note = scope_note.strip()
    with manager.store.transaction():
        delegated_target = manager.delegated_task_target(task_id)
        if note is not None and delegated_target is not None:
            raise TaskOwnedByOther(delegated_target[0])
        if status is not None:
            delegated_target = manager.assert_task_update_owner(task_id, status)
            if resume and status != "pending":
                raise ValueError("resume requires status='pending'")
            if status in {"blocked", "failed"}:
                raise ValueError(
                    f"Status {status!r} was retired: use 'cancelled' and message the requester with the reason."
                )
            if status == "in_progress":
                raise ValueError(
                    "status 'in_progress' is written only by the running TaskExec. "
                    "To (re)start a task, submit it with the submit_tasks tool. "
                    "To close it, use --status done or cancelled."
                )
            if status not in {"pending", "delegated", "done", "cancelled"}:
                raise ValueError(f"Invalid task update status: {status}")
        patch: dict[str, Any] = dict(meta_patch or {})
        if note is not None:
            current = manager.get_task_by_id(task_id)
            if current is None:
                return None
            notes = current.meta.get("scope_notes")
            updated_notes = list(notes) if isinstance(notes, list) else []
            updated_notes.append({"note": note, "at": now_iso()})
            patch["scope_notes"] = updated_notes
        entry = manager.update_meta(task_id, patch, summary=summary) if patch else None
        if patch and entry is None:
            return None
        if status is not None:
            entry = manager.update_status(task_id, status, summary=summary)
            if entry is None:
                return None
        if resume:
            entry = manager.store.resume(actor, task_id)
        if normalized_wait is not None:
            # Apply the declaration after the status transition/resume so a
            # move out of a terminal state cannot clear the row it just wrote.
            entry = manager.update_meta(task_id, {"waiting_for": normalized_wait})
            if entry is None:
                return None
            manager.store.set_waiting_for(actor, task_id, normalized_wait)

    if note is not None and entry is not None:
        payload = manager.store.get_input(actor, task_id)
        raw_requester = payload.get("reply_to") if payload else None
        if isinstance(raw_requester, dict):
            raw_requester = raw_requester.get("name")
        requester = str(raw_requester or "")
        if requester and requester != actor:
            from core.tasks.board.board_actions import notify_task_scope_note

            warning = notify_task_scope_note(actor, requester, task_id, entry.summary or task_id, note)
            if warning:
                logger.warning("Task scope-note notice failed: %s", warning)
    if status == "cancelled":
        from core.tasks.board.board_actions import notify_task_delegator, notify_task_owner

        reason = summary or t("task_update.cancel_reason_missing")
        if delegated_target is not None:
            owner, canonical_id = delegated_target
            detail = t("task_update.cancelled_by_requester", requester=actor, reason=reason)
            warning = notify_task_owner(actor, owner, canonical_id, "cancel", detail)
        else:
            detail = t("task_update.cancelled_by_owner", owner=actor, reason=reason)
            warning = notify_task_delegator(actor, actor, entry.model_dump(), task_id, "cancel", detail)
        if warning:
            logger.warning("Task cancellation notice failed: %s", warning)
    return entry


def read_tasks_via_server(
    anima_name: str, *, include_archived: bool = False, task_id: str | None = None
) -> dict[str, TaskEntry]:
    """Read a host-owned snapshot when the worker cannot access the task DB."""
    params = {"anima_name": anima_name, "include_archived": include_archived}
    if task_id is not None:
        params["task_id"] = task_id
    from core.internal_api import host_api

    response = host_api.get(
        "/api/internal/tasks",
        params=params,
        timeout=30.0,
    )
    response.raise_for_status()
    return {item["task_id"]: TaskEntry(**item) for item in response.json()["tasks"]}


def read_executable_ids_via_server(anima_name: str) -> set[str]:
    """Read execution-input availability without granting shared DB access."""
    from core.internal_api import host_api

    response = host_api.get(
        "/api/internal/tasks",
        params={"anima_name": anima_name},
        timeout=30.0,
    )
    response.raise_for_status()
    return set(response.json()["input_ids"])


def validate_task_payloads(
    anima_name: str,
    payloads: list[dict[str, Any]],
    *,
    known_ids: set[str] | None = None,
    check_dependencies: bool = True,
) -> list[dict[str, Any]]:
    """Validate the whole batch before any task becomes visible to a worker."""
    from core.config.model_catalog import validate_model_override
    from core.org.workspace import resolve_workspace

    if not payloads:
        raise ValueError("At least one task is required")
    prepared = []
    for payload in payloads:
        if not isinstance(payload, dict):
            raise ValueError("Each task must be an object")
        fields = ("task_id",) if payload.get("resume") is True else ("task_id", "title", "description")
        for field in fields:
            if not isinstance(payload.get(field), str) or not payload[field].strip():
                raise ValueError(f"Task missing required field: {field}")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:#-]{0,199}", payload["task_id"]):
            raise ValueError("Invalid task_id")
        if "resume" in payload and not isinstance(payload["resume"], bool):
            raise ValueError("resume must be a boolean")
        if payload.get("resume") is True:
            if set(payload) != {"task_id", "resume"}:
                raise ValueError("Resume accepts only task_id and resume; saved execution input is immutable")
            prepared.append(dict(payload))
            continue
        task = dict(payload)
        task.setdefault("task_type", "llm")
        if task["task_type"] != "llm":
            raise ValueError("Only LLM tasks can be published through this endpoint")
        model = task.get("model", "")
        if not isinstance(model, str):
            raise ValueError("Task model must be a string")
        if model and (error := validate_model_override(anima_name, model)):
            from core.i18n import t

            raise ValueError(f"Task {task['task_id']}: {t('tooling.model_list_hint', error=error)}")
        if "workspace" in task:
            task.setdefault("working_directory", "")
        workspace = task.get("working_directory") or task.pop("workspace", "")
        if workspace:
            task["working_directory"] = str(resolve_workspace(workspace))
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
            raise ValueError("depends_on must be a list of task IDs")
        prepared.append(task)
    _validate_task_dependencies(prepared, known_ids=known_ids, check_membership=check_dependencies)
    return prepared


def _validate_task_dependencies(
    prepared: list[dict[str, Any]],
    *,
    known_ids: set[str] | None = None,
    check_membership: bool = True,
) -> None:
    from core.tasks.pending_executor import _topological_sort

    ids = {task["task_id"] for task in prepared}
    if len(ids) != len(prepared):
        raise ValueError("Duplicate task_id found in batch")
    for task in prepared:
        if check_membership and any(dep not in ids | (known_ids or set()) for dep in task.get("depends_on", [])):
            raise ValueError(f"Task '{task['task_id']}' depends on unknown task_id")
    _topological_sort(
        [{**task, "depends_on": [dep for dep in task.get("depends_on", []) if dep in ids]} for task in prepared]
    )


def publish_tasks(
    anima_dir: Path,
    payloads: list[dict[str, Any]],
    *,
    source: Literal["human", "anima"] = "anima",
    meta: dict[str, Any] | None = None,
    host_fallback: bool = True,
) -> list[TaskEntry]:
    """Atomically publish complete tasks; a sandbox uses the existing server."""
    prepared = validate_task_payloads(anima_dir.name, payloads, check_dependencies=False)
    if source not in {"human", "anima"}:
        raise ValueError("Invalid task source")
    try:
        manager = TaskQueueManager(anima_dir)
        store = manager.store
        with store.transaction():
            existing = store.read(anima_dir.name, archived=True)
            originals = {}
            for payload in prepared:
                if payload.get("resume") is True:
                    original = store.get_input(anima_dir.name, payload["task_id"])
                    previous = existing.get(payload["task_id"])
                    if previous is None:
                        raise ValueError(f"Task not found: {payload['task_id']}")
                    if original is None:
                        raise ValueError(f"Task has no saved execution input: {payload['task_id']}")
                    if previous.status != "pending":
                        raise ValueError(
                            "Only an ended pending task may be resumed. "
                            "A cancelled or done task can be reopened with "
                            "update_task(status='pending', resume=true)."
                        )
                    validate_task_payloads(anima_dir.name, [original], check_dependencies=False)
                    originals[payload["task_id"]] = original
            _validate_task_dependencies(
                [originals.get(payload["task_id"], payload) for payload in prepared],
                known_ids=set(existing),
            )
            entries = []
            for payload in prepared:
                previous = existing.get(payload["task_id"])
                if payload.get("resume") is True:
                    original = originals[payload["task_id"]]
                    store.submit(anima_dir.name, previous, original, resume=True)
                    entries.append(store.read(anima_dir.name)[payload["task_id"]])
                    continue
                manager.submit(
                    payload,
                    source=source,
                    meta={
                        **(meta or {}),
                        **{
                            key: payload[key]
                            for key in ("model", "batch_id", "depends_on", "parallel")
                            if key in payload
                        },
                    },
                )
                entries.append(store.read(anima_dir.name, archived=True)[payload["task_id"]])
            return entries
    except (OSError, sqlite3.OperationalError, TaskPersistenceError) as exc:
        if not host_fallback or not is_task_permission_error(exc):
            raise
        result = _post_tasks(
            "submit-tasks",
            {
                "anima_name": anima_dir.name,
                "tasks": prepared,
                "source": source,
                "meta": meta or {},
            },
        )
        return [TaskEntry(**item) for item in result["tasks"]]


def publish_delegation(
    target_dir: Path,
    payload: dict[str, Any],
    *,
    delegator: str,
    tracking_task_id: str,
    host_fallback: bool = True,
) -> bool:
    """Publish task + alias atomically. Return whether the host proxy was used."""
    prepared = validate_task_payloads(target_dir.name, [payload])[0]
    prepared.setdefault("relay_chain", [delegator])
    try:
        manager = TaskQueueManager(target_dir)
        with manager.store.transaction():
            manager.submit(prepared, meta={"model": payload.get("model", "")})
            manager.store.alias(delegator, tracking_task_id, target_dir.name, payload["task_id"])
        return False
    except (OSError, sqlite3.OperationalError, TaskPersistenceError) as exc:
        if not host_fallback or not is_task_permission_error(exc):
            raise
        _post_tasks(
            "delegate-task",
            {
                "delegator": delegator,
                "target": target_dir.name,
                "instruction": prepared["description"],
                "summary": prepared["title"],
                "sub_task_id": prepared["task_id"],
                "tracking_task_id": tracking_task_id,
                "workspace": prepared.get("working_directory", ""),
                "acceptance_criteria": prepared.get("acceptance_criteria", []),
                "model": prepared.get("model", ""),
                "execution_input": prepared,
            },
        )
        return True
