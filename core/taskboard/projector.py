"""Projection from per-Anima task queues into TaskBoard rows."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from core.memory.task_queue import TaskEntry, TaskQueueManager
from core.paths import get_animas_dir
from core.taskboard.models import AttentionVisibility, BoardColumn, BoardTask, TaskBoardMetadata
from core.taskboard.store import TaskBoardStore

QUEUE_STATUS_TO_COLUMN: dict[str, BoardColumn] = {
    "pending": BoardColumn.TODO,
    "in_progress": BoardColumn.RUNNING,
    "blocked": BoardColumn.BLOCKED,
    "delegated": BoardColumn.WAITING,
    "failed": BoardColumn.REVIEW,
    "done": BoardColumn.DONE,
    "cancelled": BoardColumn.DONE,
}

ARCHIVED_QUEUE_STATUSES = {"done", "cancelled"}

_COLUMN_ORDER = {column: index for index, column in enumerate(BoardColumn)}

# A task is "needs_human" when progress is gated on a human action.
_TERMINAL_QUEUE_STATUSES = {"done", "cancelled", "failed"}
_HUMAN_BLOCKER_VALUES = {"human", "user", "owner"}
_HUMAN_BLOCKER_KEYS = ("blocker", "blocked_on", "waiting_for", "waiting_on")


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

    return sorted(projected, key=_sort_key)


def project_all(
    animas_dir: Path | str | None = None,
    store: TaskBoardStore | None = None,
    *,
    anima_names: Iterable[str] | None = None,
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
            )
        )
    return sorted(projected, key=_sort_key)


def _discover_anima_names(animas_dir: Path) -> set[str]:
    if not animas_dir.exists():
        return set()
    return {path.name for path in animas_dir.iterdir() if path.is_dir()}


def _load_queue_tasks(anima_dir: Path) -> list[TaskEntry]:
    manager = TaskQueueManager(anima_dir)
    # list_tasks() intentionally hides terminal tasks; TaskBoard needs a full
    # replay to decide whether those entries should be archived.
    return list(manager._load_all().values())


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

    needs_human, needs_human_reason = compute_needs_human(
        assignee=task.assignee,
        queue_status=task.status,
        meta=task.meta,
        notification_key=metadata.notification_key if metadata is not None else None,
    )

    return BoardTask(
        anima_name=anima_name,
        task_id=task.task_id,
        queue_missing=False,
        source=task.source,
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
    )


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
