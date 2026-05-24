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
_MONITORING_SNAPSHOT_KINDS = {
    "monitoring_snapshot",
    "heartbeat_snapshot",
    "status_snapshot",
    "evidence_snapshot",
}
_MONITORING_SNAPSHOT_MARKERS = (
    "inbox未読",
    "governor",
    "usage governor",
    "state/pending",
    "background_notifications",
    "未読滞留なし",
    "緊急通知不要",
    "追加催促",
    "再投入なし",
    "固定観察範囲",
    "evidence-only monitoring",
    "task_results",
)


def is_monitoring_snapshot_task(task: TaskEntry, *, anima_name: str | None = None) -> bool:
    """Return True for non-actionable heartbeat/status observation snapshots."""
    meta = task.meta or {}
    raw_kind = meta.get("taskboard_kind") or meta.get("task_kind") or meta.get("kind")
    if isinstance(raw_kind, str) and raw_kind.strip().lower() in _MONITORING_SNAPSHOT_KINDS:
        return True
    if bool(meta.get("monitoring_snapshot")) or bool(meta.get("non_actionable_monitoring")):
        return True

    task_desc = meta.get("task_desc") if isinstance(meta.get("task_desc"), dict) else {}
    title = str(task_desc.get("title") or task.summary or "")
    description = str(task_desc.get("description") or task.original_instruction or "")
    text = f"{title}\n{description}".casefold()
    marker_count = sum(1 for marker in _MONITORING_SNAPSHOT_MARKERS if marker.casefold() in text)
    if marker_count < 3:
        return False

    if "heartbeat:" in text or "heartbeat：" in text:
        return True

    if anima_name and task.assignee != anima_name:
        return False
    return "監視" in text or "観察" in text or "monitoring" in text


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
    is_monitoring_snapshot = is_monitoring_snapshot_task(task, anima_name=anima_name)
    if is_monitoring_snapshot:
        default_visibility = AttentionVisibility.ARCHIVED
        default_column = BoardColumn.SUPPRESSED
    else:
        default_visibility = (
            AttentionVisibility.ARCHIVED if task.status in ARCHIVED_QUEUE_STATUSES else AttentionVisibility.ACTIVE
        )
    visibility = metadata.visibility if metadata is not None else default_visibility
    column = metadata.column if metadata is not None and metadata.column is not None else default_column

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
    )


def _project_missing_task(metadata: TaskBoardMetadata) -> BoardTask:
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
