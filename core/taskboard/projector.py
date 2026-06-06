"""Projection from per-Anima task queues into TaskBoard rows."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from core.memory.task_queue import (
    _STALE_TASK_THRESHOLD_SEC,
    TaskEntry,
    TaskQueueManager,
    _elapsed_seconds,
)
from core.paths import get_animas_dir
from core.taskboard.models import AttentionVisibility, BoardColumn, BoardTask, BoardTaskLink, TaskBoardMetadata
from core.taskboard.store import TaskBoardStore
from core.time_utils import now_local

QUEUE_STATUS_TO_COLUMN: dict[str, BoardColumn] = {
    "pending": BoardColumn.TODO,
    "in_progress": BoardColumn.RUNNING,
    "blocked": BoardColumn.BLOCKED,
    "delegated": BoardColumn.WAITING,
    "failed": BoardColumn.BLOCKED,
    "done": BoardColumn.DONE,
    "cancelled": BoardColumn.DONE,
}

MACHINE_INSTRUCTION_ORIGINS = frozenset({"daily-ops-dashboard"})

ARCHIVED_QUEUE_STATUSES = {"done", "cancelled"}

_COLUMN_ORDER = {column: index for index, column in enumerate(BoardColumn)}

# A task is "needs_human" when progress is gated on a human action.
_TERMINAL_QUEUE_STATUSES = {"done", "cancelled", "failed"}
_HUMAN_BLOCKER_VALUES = {"human", "user", "owner"}
_HUMAN_BLOCKER_KEYS = ("blocker", "blocked_on", "waiting_for", "waiting_on")
_TASK_ID_RE = re.compile(r"\b[0-9a-f]{8,16}\b", re.IGNORECASE)


def compute_needs_human(
    *,
    assignee: str | None,
    queue_status: str | None,
    meta: dict | None,
    notification_key: str | None,
) -> tuple[bool, str | None]:
    """Return (needs_human, reason_code) for a projected task.

    Detection rules:
      * C: assignee resolves to "human"/"user".
      * B: a call_human notification is registered and the queue task is not terminal.
      * D: meta carries an explicit flag (``needs_human``) or a human-valued
        blocker key on a blocked task.
    """
    if (assignee or "").strip().lower() in _HUMAN_BLOCKER_VALUES:
        return True, "assignee_human"

    if notification_key and (queue_status or "") not in _TERMINAL_QUEUE_STATUSES:
        return True, "call_human_pending"

    if meta:
        if bool(meta.get("needs_human")):
            return True, "meta_flag"
        if queue_status == "blocked":
            for key in _HUMAN_BLOCKER_KEYS:
                value = meta.get(key)
                if isinstance(value, str) and value.strip().lower() in _HUMAN_BLOCKER_VALUES:
                    return True, "meta_blocker"

    return False, None


def project_anima(
    anima_dir: Path | str,
    store: TaskBoardStore | None = None,
    *,
    anima_name: str | None = None,
    include_missing: bool = False,
    include_archived: bool = False,
    attach_relations: bool = True,
) -> list[BoardTask]:
    """Project one Anima's task_queue.jsonl into BoardTask rows."""
    resolved_anima_dir = Path(anima_dir)
    resolved_anima_name = anima_name or resolved_anima_dir.name
    resolved_store = store or TaskBoardStore()

    metadata_rows = resolved_store.list_metadata(anima_name=resolved_anima_name)
    metadata_by_task_id = {metadata.task_id: metadata for metadata in metadata_rows}

    tasks = _load_queue_tasks(resolved_anima_dir)
    projected: list[BoardTask] = []
    seen_task_ids: set[str] = set()
    for task in tasks:
        seen_task_ids.add(task.task_id)
        board_task = _project_queue_task(
            task=task,
            anima_name=resolved_anima_name,
            metadata=metadata_by_task_id.get(task.task_id),
        )
        if _should_include(board_task, include_archived=include_archived):
            projected.append(board_task)

    if include_missing:
        for metadata in metadata_rows:
            if metadata.task_id in seen_task_ids:
                continue
            board_task = _project_missing_task(metadata)
            if _should_include(board_task, include_archived=include_archived):
                projected.append(board_task)

    if attach_relations:
        _attach_related_tasks(
            projected,
            _build_task_index(resolved_anima_dir.parent, [resolved_anima_name], resolved_store),
        )
    _mark_serial_pending_backlog(projected)
    _suppress_duplicate_failed_crons(projected)
    _suppress_duplicate_delegated_parents(projected)
    return sorted(
        [task for task in projected if _should_include(task, include_archived=include_archived)],
        key=_sort_key,
    )


def project_all(
    animas_dir: Path | str | None = None,
    store: TaskBoardStore | None = None,
    *,
    anima_names: Iterable[str] | None = None,
    relation_anima_names: Iterable[str] | None = None,
    include_missing: bool = False,
    include_archived: bool = False,
) -> list[BoardTask]:
    """Project all selected Anima task queues into BoardTask rows."""
    resolved_animas_dir = Path(animas_dir) if animas_dir is not None else get_animas_dir()
    resolved_store = store or TaskBoardStore()
    names = set(anima_names) if anima_names is not None else _discover_anima_names(resolved_animas_dir)

    if include_missing and anima_names is None:
        names.update(metadata.anima_name for metadata in resolved_store.list_metadata())

    projected: list[BoardTask] = []
    for name in sorted(names):
        projected.extend(
            project_anima(
                resolved_animas_dir / name,
                resolved_store,
                anima_name=name,
                include_missing=include_missing,
                include_archived=include_archived,
                attach_relations=False,
            )
        )
    relation_names = set(relation_anima_names) if relation_anima_names is not None else names
    _attach_related_tasks(projected, _build_task_index(resolved_animas_dir, relation_names, resolved_store))
    _mark_serial_pending_backlog(projected)
    _suppress_duplicate_failed_crons(projected)
    _suppress_duplicate_delegated_parents(projected)
    return sorted(
        [task for task in projected if _should_include(task, include_archived=include_archived)],
        key=_sort_key,
    )


def _discover_anima_names(animas_dir: Path) -> set[str]:
    if not animas_dir.exists():
        return set()
    return {path.name for path in animas_dir.iterdir() if path.is_dir()}


def _load_queue_tasks(anima_dir: Path) -> list[TaskEntry]:
    manager = TaskQueueManager(anima_dir)
    # list_tasks() intentionally hides terminal tasks; TaskBoard needs a full
    # replay to decide whether those entries should be archived.
    return list(manager._load_all().values())


def _load_archived_queue_tasks(anima_dir: Path) -> list[TaskEntry]:
    archive_path = anima_dir / "state" / "task_queue_archive.jsonl"
    if not archive_path.exists():
        return []
    tasks: dict[str, TaskEntry] = {}
    try:
        raw_text = archive_path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    for line in raw_text.splitlines():
        raw_line = line.strip()
        if not raw_line:
            continue
        try:
            raw = json.loads(raw_line)
            task = TaskEntry(**raw)
        except Exception:
            continue
        tasks[task.task_id] = task
    return list(tasks.values())


def _build_task_index(
    animas_dir: Path,
    anima_names: Iterable[str],
    store: TaskBoardStore,
) -> dict[tuple[str, str], BoardTask]:
    """Build a broad task lookup for relation labels, including archived rows."""
    index: dict[tuple[str, str], BoardTask] = {}
    for name in sorted(set(anima_names)):
        metadata_rows = {metadata.task_id: metadata for metadata in store.list_metadata(anima_name=name)}
        anima_dir = animas_dir / name
        if anima_dir.is_dir():
            for task in _load_queue_tasks(anima_dir):
                index[(name, task.task_id)] = _project_queue_task(
                    task=task,
                    anima_name=name,
                    metadata=metadata_rows.get(task.task_id),
                )
            for task in _load_archived_queue_tasks(anima_dir):
                index.setdefault(
                    (name, task.task_id),
                    _project_queue_task(
                        task=task,
                        anima_name=name,
                        metadata=metadata_rows.get(task.task_id),
                    ),
                )
        for metadata in metadata_rows.values():
            index.setdefault((name, metadata.task_id), _project_missing_task(metadata))
    return index


def _attach_related_tasks(
    tasks: list[BoardTask],
    index: dict[tuple[str, str], BoardTask],
) -> None:
    if not tasks or not index:
        return

    delegated_parent_by_child: dict[tuple[str, str], BoardTask] = {}
    for candidate in index.values():
        meta = candidate.meta or {}
        target = meta.get("delegated_to")
        child_id = meta.get("delegated_task_id")
        if isinstance(target, str) and target and isinstance(child_id, str) and child_id:
            delegated_parent_by_child[(target, child_id)] = candidate

    for task in tasks:
        links: list[BoardTaskLink] = []
        seen: set[tuple[str, str, str]] = set()

        meta = task.meta or {}
        target = meta.get("delegated_to")
        child_id = meta.get("delegated_task_id")
        if isinstance(target, str) and target and isinstance(child_id, str) and child_id:
            related_child = index.get((target, child_id))
            _append_link(
                links,
                seen,
                kind="delegates_to",
                related=related_child,
                fallback_anima_name=target,
                fallback_task_id=child_id,
                peer_name=target,
            )
            if related_child is not None and task.queue_status not in _TERMINAL_QUEUE_STATUSES:
                if related_child.queue_status in _TERMINAL_QUEUE_STATUSES:
                    if _delegated_child_needs_followup(related_child):
                        task.column = BoardColumn.BLOCKED
                    elif task.column != BoardColumn.BLOCKED:
                        task.column = BoardColumn.REVIEW
                elif task.column == BoardColumn.BLOCKED:
                    task.column = BoardColumn.WAITING

        parent = delegated_parent_by_child.get((task.anima_name, task.task_id))
        if parent is not None:
            _append_link(
                links,
                seen,
                kind="delegated_from",
                related=parent,
                fallback_anima_name=parent.anima_name,
                fallback_task_id=parent.task_id,
                peer_name=parent.anima_name,
            )
            if task.queue_status == "failed" and _is_cancelled_or_tombstoned_parent(parent):
                task.visibility = AttentionVisibility.ARCHIVED
                task.column = BoardColumn.SUPPRESSED
                task.replaced_by = f"{parent.anima_name}:{parent.task_id}"
                task.tombstone_reason = "delegated_parent_cancelled"

        source_from = meta.get("source_from")
        referenced_tasks = _find_referenced_tasks(task, index)
        for related in referenced_tasks:
            _append_link(
                links,
                seen,
                kind="responds_to",
                related=related,
                fallback_anima_name=related.anima_name,
                fallback_task_id=related.task_id,
                peer_name=source_from if isinstance(source_from, str) and source_from else related.anima_name,
            )
        summary_referenced_tasks = _find_referenced_tasks(task, index, include_original_instruction=False)
        if task.column == BoardColumn.BLOCKED and any(
            related.queue_status not in _TERMINAL_QUEUE_STATUSES for related in summary_referenced_tasks
        ):
            task.column = BoardColumn.WAITING

        task.related_tasks = links


def _suppress_duplicate_delegated_parents(tasks: list[BoardTask]) -> None:
    groups: dict[tuple[str, str, str], list[BoardTask]] = {}
    for task in tasks:
        if task.visibility != AttentionVisibility.ACTIVE or task.queue_status not in {"delegated", "blocked"}:
            continue
        meta = task.meta or {}
        target = meta.get("delegated_to")
        child_id = meta.get("delegated_task_id")
        if not isinstance(target, str) or not target or not isinstance(child_id, str) or not child_id:
            continue
        groups.setdefault((task.anima_name, target, child_id), []).append(task)

    for duplicates in groups.values():
        if len(duplicates) <= 1:
            continue
        keeper = max(duplicates, key=_delegated_parent_precedence)
        for task in duplicates:
            if task is keeper:
                continue
            task.visibility = AttentionVisibility.ARCHIVED
            task.column = BoardColumn.SUPPRESSED
            task.replaced_by = f"{keeper.anima_name}:{keeper.task_id}"
            task.tombstone_reason = "duplicate_delegated_parent"


def _mark_serial_pending_backlog(tasks: list[BoardTask]) -> None:
    running_animas = {
        task.anima_name
        for task in tasks
        if task.visibility == AttentionVisibility.ACTIVE and task.queue_status == "in_progress"
    }
    if not running_animas:
        return

    for task in tasks:
        if (
            task.visibility == AttentionVisibility.ACTIVE
            and task.queue_status == "pending"
            and task.column == BoardColumn.REVIEW
            and task.anima_name in running_animas
        ):
            task.column = BoardColumn.WAITING


def _suppress_duplicate_failed_crons(tasks: list[BoardTask]) -> None:
    groups: dict[tuple[str, str], list[BoardTask]] = {}
    for task in tasks:
        if (
            task.visibility != AttentionVisibility.ACTIVE
            or task.queue_status != "failed"
            or not task.is_from_cron
            or not task.cron_task_name
        ):
            continue
        groups.setdefault((task.anima_name, task.cron_task_name), []).append(task)

    for duplicates in groups.values():
        if len(duplicates) <= 1:
            continue
        keeper = max(duplicates, key=_task_updated_precedence)
        for task in duplicates:
            if task is keeper:
                continue
            task.visibility = AttentionVisibility.ARCHIVED
            task.column = BoardColumn.SUPPRESSED
            task.replaced_by = f"{keeper.anima_name}:{keeper.task_id}"
            task.tombstone_reason = "duplicate_failed_cron"


def _is_cancelled_or_tombstoned_parent(parent: BoardTask) -> bool:
    return parent.queue_status == "cancelled" or parent.visibility == AttentionVisibility.TOMBSTONED


def _delegated_child_needs_followup(child: BoardTask) -> bool:
    if child.queue_status in {"failed", "cancelled"}:
        return True
    if child.queue_status != "done":
        return False

    summary_text = " ".join((child.summary or "").strip().split()).casefold()
    combined_text = " ".join(
        part
        for part in (
            child.summary or "",
            child.original_instruction or "",
        )
        if part
    ).casefold()
    failure_markers = (
        "failed:",
        "blocked:",
        " fail",
        "| fail",
        "fail (",
        "not final",
        "not final evidence",
        "not final completion",
        "no final response",
        "tool error",
        "tool call(s)",
        "errors=",
    )
    progress_markers = (
        "next step",
        "next action",
        "will proceed",
        "will create",
        "will write",
        "will run",
        "let me",
        "schema confirmation",
        "checking schema",
        "creating a script",
        "create a fixed script",
        "スキーマが確認できました",
        "修正版スクリプトを作成します",
        "machineで",
        "調査します",
        "実施します",
        "更新に進む",
        "保存してdiscordに投稿する",
    )
    return any(marker in combined_text for marker in failure_markers) or any(
        marker in summary_text for marker in progress_markers
    )


def _delegated_parent_precedence(task: BoardTask) -> tuple[int, str, str]:
    summary = (task.summary or "").strip().casefold()
    is_superseded = summary.startswith("superseded by")
    updated_at = task.queue_updated_at or task.board_updated_at or ""
    return (0 if is_superseded else 1, updated_at, task.task_id)


def _task_updated_precedence(task: BoardTask) -> tuple[str, str]:
    updated_at = task.queue_updated_at or task.board_updated_at or ""
    return (updated_at, task.task_id)


def _append_link(
    links: list[BoardTaskLink],
    seen: set[tuple[str, str, str]],
    *,
    kind: str,
    related: BoardTask | None,
    fallback_anima_name: str,
    fallback_task_id: str,
    peer_name: str | None,
) -> None:
    key = (kind, fallback_anima_name, fallback_task_id)
    if key in seen:
        return
    seen.add(key)
    links.append(
        BoardTaskLink(
            kind=kind,
            anima_name=related.anima_name if related is not None else fallback_anima_name,
            task_id=related.task_id if related is not None else fallback_task_id,
            title=_title_for_link(related) if related is not None else None,
            peer_name=peer_name,
        )
    )


def _find_referenced_tasks(
    task: BoardTask,
    index: dict[tuple[str, str], BoardTask],
    *,
    include_original_instruction: bool = True,
) -> list[BoardTask]:
    text_parts = [
        task.summary,
        str((task.meta or {}).get("source_task_id") or ""),
        str((task.meta or {}).get("reply_to_task_id") or ""),
    ]
    if include_original_instruction:
        text_parts.append(task.original_instruction)
    ids = []
    for text in text_parts:
        if not text:
            continue
        ids.extend(match.group(0) for match in _TASK_ID_RE.finditer(text))

    found: list[BoardTask] = []
    seen: set[tuple[str, str]] = set()
    for task_id in ids:
        for key, candidate in index.items():
            if candidate.task_id != task_id or key == (task.anima_name, task.task_id):
                continue
            if key in seen:
                continue
            seen.add(key)
            found.append(candidate)
    return found


def _title_for_link(task: BoardTask | None) -> str | None:
    if task is None:
        return None
    summary = _compact_relation_title(task.summary)
    if summary and "\n" not in (task.summary or "") and len(task.summary or "") <= 160:
        return summary
    return _compact_relation_title(task.original_instruction) or summary


def _compact_relation_title(value: str | None) -> str | None:
    if not value:
        return None
    line = " ".join(value.strip().split())
    if not line:
        return None
    return line[:180]


def _project_queue_task(
    *,
    task: TaskEntry,
    anima_name: str,
    metadata: TaskBoardMetadata | None,
) -> BoardTask:
    default_column = QUEUE_STATUS_TO_COLUMN.get(task.status, BoardColumn.TODO)
    default_visibility = (
        AttentionVisibility.ARCHIVED if task.status in ARCHIVED_QUEUE_STATUSES else AttentionVisibility.ACTIVE
    )
    visibility = metadata.visibility if metadata is not None else default_visibility
    column = metadata.column if metadata is not None and metadata.column is not None else default_column
    if (
        task.status in {"pending", "in_progress"}
        and column in {BoardColumn.TODO, BoardColumn.RUNNING}
        and _is_stale_queue_task(task)
    ):
        # Stale active work needs triage, but it is not the same thing as a
        # queue task explicitly marked blocked.
        column = BoardColumn.REVIEW

    needs_human, needs_human_reason = compute_needs_human(
        assignee=task.assignee,
        queue_status=task.status,
        meta=task.meta,
        notification_key=metadata.notification_key if metadata is not None else None,
    )

    task_meta = task.meta or {}
    is_from_cron = bool(task_meta.get("from_cron"))
    cron_task_name = task_meta.get("cron_task_name") if is_from_cron else None

    return BoardTask(
        anima_name=anima_name,
        task_id=task.task_id,
        queue_missing=False,
        source=task.source,
        instruction_origin=_resolve_instruction_origin(task),
        original_instruction=task.original_instruction,
        assignee=task.assignee,
        queue_status=task.status,
        summary=task.summary,
        deadline=task.deadline,
        relay_chain=task.relay_chain,
        meta=task.meta,
        queue_updated_at=task.updated_at,
        visibility=visibility,
        column=column,
        position=metadata.position if metadata is not None else None,
        expires_at=metadata.expires_at if metadata is not None else None,
        snoozed_until=metadata.snoozed_until if metadata is not None else None,
        last_notified_at=metadata.last_notified_at if metadata is not None else None,
        notification_key=metadata.notification_key if metadata is not None else None,
        surface_count=metadata.surface_count if metadata is not None else 0,
        source_ref=_resolve_source_ref(anima_name=anima_name, task_id=task.task_id, metadata=metadata),
        replaced_by=metadata.replaced_by if metadata is not None else None,
        tombstone_reason=metadata.tombstone_reason if metadata is not None else None,
        board_updated_at=metadata.updated_at if metadata is not None else None,
        board_updated_by=metadata.updated_by if metadata is not None else None,
        needs_human=needs_human,
        needs_human_reason=needs_human_reason,
        is_from_cron=is_from_cron,
        cron_task_name=cron_task_name if isinstance(cron_task_name, str) else None,
    )


def _resolve_instruction_origin(task: TaskEntry) -> str | None:
    """Return the display-level instruction origin for TaskBoard provenance."""
    if task.source != "human":
        return None

    meta = task.meta or {}
    explicit = meta.get("instruction_origin")
    if explicit in {"human", "machine"}:
        return str(explicit)

    meta_origin = meta.get("origin")
    if isinstance(meta_origin, str) and meta_origin in MACHINE_INSTRUCTION_ORIGINS:
        return "machine"
    if any(origin in MACHINE_INSTRUCTION_ORIGINS for origin in task.relay_chain):
        return "machine"
    if meta.get("daily_ops_dedup_key"):
        return "machine"

    return "human"


def _is_stale_queue_task(task: TaskEntry) -> bool:
    elapsed_sec = _elapsed_seconds(task.updated_at or "", now_local())
    return elapsed_sec is not None and elapsed_sec >= _STALE_TASK_THRESHOLD_SEC


def _project_missing_task(metadata: TaskBoardMetadata) -> BoardTask:
    needs_human, needs_human_reason = compute_needs_human(
        assignee=metadata.anima_name,
        queue_status=None,
        meta=None,
        notification_key=metadata.notification_key,
    )
    return BoardTask(
        anima_name=metadata.anima_name,
        task_id=metadata.task_id,
        queue_missing=True,
        assignee=metadata.anima_name,
        visibility=metadata.visibility,
        column=metadata.column or BoardColumn.SUPPRESSED,
        position=metadata.position,
        expires_at=metadata.expires_at,
        snoozed_until=metadata.snoozed_until,
        last_notified_at=metadata.last_notified_at,
        notification_key=metadata.notification_key,
        surface_count=metadata.surface_count,
        source_ref=metadata.source_ref or _source_ref(metadata.anima_name, metadata.task_id),
        replaced_by=metadata.replaced_by,
        tombstone_reason=metadata.tombstone_reason,
        board_updated_at=metadata.updated_at,
        board_updated_by=metadata.updated_by,
        needs_human=needs_human,
        needs_human_reason=needs_human_reason,
    )


def _should_include(task: BoardTask, *, include_archived: bool) -> bool:
    if include_archived:
        return True
    return task.visibility == AttentionVisibility.ACTIVE


def _resolve_source_ref(
    *,
    anima_name: str,
    task_id: str,
    metadata: TaskBoardMetadata | None,
) -> str:
    if metadata is not None and metadata.source_ref:
        return metadata.source_ref
    return _source_ref(anima_name, task_id)


def _source_ref(anima_name: str, task_id: str) -> str:
    return f"task_queue:{anima_name}:{task_id}"


def _sort_key(task: BoardTask) -> tuple[int, float, str, str, str]:
    position = task.position if task.position is not None else float("inf")
    updated_at = task.queue_updated_at or task.board_updated_at or ""
    return (_COLUMN_ORDER.get(task.column, 999), position, updated_at, task.anima_name, task.task_id)
