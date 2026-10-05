"""Single TaskBoard view built directly from the canonical TaskStore.

There is no separate presentation metadata: every row is derived from the ``tasks``
and ``task_aliases`` tables. Delegated work appears as a ``WAITING`` row only
while its canonical task is still active, so a completed delegation cannot leave a
'ghost waiting' card behind.
"""

from __future__ import annotations

from collections.abc import Iterable

from core.tasks.board.models import BoardColumn, BoardRow
from core.tasks.board.tasks import TaskStore

_TERMINAL_STATUSES = frozenset({"done", "cancelled"})


def _status_to_column(status: str, waiting: bool) -> BoardColumn:
    if waiting:
        return BoardColumn.WAITING
    if status == "pending":
        return BoardColumn.TODO
    if status == "in_progress":
        return BoardColumn.RUNNING
    return BoardColumn.DONE


def _sort_key(row: BoardRow) -> tuple:
    column_rank = {
        BoardColumn.TODO: 0,
        BoardColumn.RUNNING: 1,
        BoardColumn.WAITING: 2,
        BoardColumn.DONE: 3,
    }[row.column]
    # Human-sourced first, then oldest update.
    return (column_rank, 0 if row.source == "human" else 1, row.updated_at)


def list_board(
    store: TaskStore,
    *,
    owner: str | None = None,
    viewer: str | None = None,
    all_viewers: bool = False,
    history_limit: int = 0,
    q: str | None = None,
) -> list[BoardRow]:
    """Return the unified board view: active canonical rows plus optional history.

    ``owner`` filters canonical rows to one anima; ``viewer`` adds that anima's
    alias rows; ``all_viewers`` adds every viewer's alias rows. ``history_limit``
    appends that many most-recent terminal rows under ``DONE``.
    """
    rows = store.board_rows(anima=owner, viewer=viewer, all_viewers=all_viewers)
    if history_limit > 0:
        rows.extend(store.history_rows(owner, history_limit))

    board: list[BoardRow] = []
    for row in rows:
        status = row.get("status") or "pending"
        waiting = bool(row.get("waiting"))
        board.append(
            BoardRow(
                anima_name=row["anima"],
                task_id=row.get("task_id") or row["canonical_task_id"],
                canonical_task_id=row["canonical_task_id"],
                assignee=row.get("assignee"),
                source=row.get("source"),
                summary=row.get("summary"),
                original_instruction=row.get("original_instruction"),
                queue_status=status,
                relay_chain=list(row.get("relay_chain") or []),
                meta=dict(row.get("meta") or {}),
                updated_at=row.get("updated_at") or "",
                column=_status_to_column(status, waiting),
                visibility="archived" if status in _TERMINAL_STATUSES else "active",
                waiting=waiting,
                lease=row.get("lease"),
            )
        )

    if q:
        needle = q.casefold()
        board = [
            row
            for row in board
            if needle in (row.summary or "").casefold() or needle in (row.original_instruction or "").casefold()
        ]

    done_rows = [row for row in board if row.column == BoardColumn.DONE]
    active_rows = [row for row in board if row.column != BoardColumn.DONE]
    active_rows.sort(key=_sort_key)
    done_rows.sort(key=lambda row: row.updated_at, reverse=True)  # newest first
    board = active_rows + done_rows
    return board


def summarize_board(store: TaskStore, anima_names: Iterable[str]) -> dict[str, int]:
    """Count active canonical work without double-counting delegations.

    ``pending`` / ``in_progress`` count canonical rows only; ``delegated`` counts
    alias (WAITING) rows whose canonical task is still active (a reference
    count); ``total_active`` is the sum of canonical active rows.
    """
    summary: dict[str, int] = {"pending": 0, "in_progress": 0, "delegated": 0, "total_active": 0}
    for name in anima_names:
        for row in store.board_rows(anima=name, viewer=name):
            if row.get("waiting"):
                summary["delegated"] += 1
                continue
            status = row.get("status")
            if status == "pending":
                summary["pending"] += 1
            elif status == "in_progress":
                summary["in_progress"] += 1
    summary["total_active"] = summary["pending"] + summary["in_progress"]
    return summary
