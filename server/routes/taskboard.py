from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.tasks.board.board_actions import BoardActionError, find_task_matches, run_board_action
from core.tasks.board.models import BoardColumn, BoardRow
from core.tasks.board.tasks import TaskStore, open_task_store
from core.tasks.board.view import list_board, summarize_board

logger = logging.getLogger("animaworks.routes.taskboard")

DEFAULT_HISTORY_LIMIT = 500
MAX_HISTORY_LIMIT = 5000
_COLUMN_TITLES = {
    BoardColumn.TODO: "Todo",
    BoardColumn.RUNNING: "Running",
    BoardColumn.WAITING: "Waiting",
    BoardColumn.DONE: "Done",
}


class CancelTaskRequest(BaseModel):
    reason: str = Field(min_length=1)


def create_taskboard_router() -> APIRouter:
    router = APIRouter()

    @router.get("/task-board")
    async def list_task_board(
        request: Request,
        assignee: str | None = None,
        column: BoardColumn | None = None,
        include_archived: bool = False,
        q: str | None = None,
        history_limit: int = Query(DEFAULT_HISTORY_LIMIT, ge=0, le=MAX_HISTORY_LIMIT),
    ) -> dict[str, Any]:
        """Return the unified TaskBoard view read straight from the canonical TaskStore."""
        try:
            return await asyncio.to_thread(
                _list_task_board,
                request,
                assignee=assignee,
                column=column,
                include_archived=include_archived,
                q=q,
                history_limit=history_limit,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("TaskBoard list failed")
            raise HTTPException(
                status_code=500,
                detail={"error": "taskboard_unavailable", "message": "TaskBoard API failed"},
            ) from exc

    @router.get("/task-board/summary")
    async def get_task_board_summary(request: Request) -> dict[str, int]:
        """Return TaskBoard summary counts for dashboard use."""
        try:
            paths = _resolve_paths(request)
            store = _store_for(paths["shared_dir"], read_only=True)
            return await asyncio.to_thread(summarize_board, store, paths["anima_names"])
        except Exception as exc:
            logger.exception("TaskBoard summary failed")
            raise HTTPException(
                status_code=500,
                detail={"error": "taskboard_unavailable", "message": "TaskBoard API failed"},
            ) from exc

    @router.post("/task-board/{anima_name}/{task_id}/cancel")
    async def cancel_task(
        request: Request,
        anima_name: str,
        task_id: str,
        payload: CancelTaskRequest,
    ) -> dict[str, Any]:
        """Explicitly cancel a task, overriding any outstanding lease (human operation)."""
        try:
            return await asyncio.to_thread(_cancel_task, request, anima_name, task_id, payload)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("TaskBoard cancel failed")
            raise HTTPException(
                status_code=500,
                detail={"error": "taskboard_unavailable", "message": "TaskBoard API failed"},
            ) from exc

    return router


def _list_task_board(
    request: Request,
    *,
    assignee: str | None,
    column: BoardColumn | None,
    include_archived: bool,
    q: str | None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    paths = _resolve_paths(request)
    animas_dir = paths["animas_dir"]
    anima_names = paths["anima_names"]
    selected_names = _selected_anima_names(animas_dir, anima_names, assignee)
    store = _store_for(paths["shared_dir"], read_only=True)
    limit = history_limit if include_archived else 0
    if assignee is None:
        rows = list_board(store, all_viewers=True, history_limit=limit, q=q)
        owner: str | None = None
    else:
        rows = list_board(store, owner=assignee, viewer=assignee, history_limit=limit, q=q)
        owner = assignee

    if column is not None:
        rows = [row for row in rows if row.column == column]

    tasks = [row.model_dump(mode="json") for row in rows]
    return {
        "columns": _column_response(rows),
        "tasks": tasks,
        "counts": {
            "active": sum(1 for row in rows if row.visibility == "active"),
            "archived": sum(1 for row in rows if row.visibility == "archived"),
        },
        "meta": {
            "history_limit": history_limit if include_archived else None,
            "history_truncated": _history_truncated(store, owner, limit),
            "warnings": {
                "corrupt_task_queue_lines": _count_corrupt_task_queue_lines(animas_dir, selected_names),
            },
        },
    }


def _cancel_task(request: Request, anima_name: str, task_id: str, payload: CancelTaskRequest) -> dict[str, Any]:
    paths = _resolve_paths(request)
    _ensure_known_anima(paths["animas_dir"], paths["anima_names"], anima_name)
    store = _store_for(paths["shared_dir"], read_only=False)
    if not find_task_matches(store, task_id, owner=anima_name):
        raise HTTPException(status_code=404, detail={"error": "task_not_found", "task_id": task_id})
    actor = _resolve_actor(request, None, default="human")
    try:
        result = run_board_action(
            actor=actor,
            action="cancel",
            task_id=task_id,
            text=payload.reason,
            owner=anima_name,
            override_lease=True,
            store=store,
        )
    except BoardActionError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "board_action_refused", "message": exc.message},
        ) from exc
    return {"ok": True, "result": result}


def _resolve_actor(request: Request, requested_actor: str | None, *, default: str) -> str:
    user = getattr(request.state, "user", None)
    username = getattr(user, "username", None)
    if username:
        return str(username)
    return requested_actor or default


def _resolve_paths(request: Request) -> dict[str, Any]:
    animas_dir = Path(request.app.state.animas_dir)
    shared_dir = Path(getattr(request.app.state, "shared_dir", animas_dir.parent / "shared"))
    raw_names = getattr(request.app.state, "anima_names", None)
    if raw_names is None:
        anima_names = sorted(path.name for path in animas_dir.iterdir() if path.is_dir()) if animas_dir.exists() else []
    else:
        anima_names = list(raw_names)
    return {"animas_dir": animas_dir, "shared_dir": shared_dir, "anima_names": anima_names}


def _store_for(shared_dir: Path, *, read_only: bool) -> TaskStore:
    return open_task_store(shared_dir / "taskboard.sqlite3", read_only=read_only)


def _selected_anima_names(animas_dir: Path, anima_names: list[str], assignee: str | None) -> list[str]:
    if assignee is None:
        return sorted(set(anima_names))
    _ensure_known_anima(animas_dir, anima_names, assignee)
    return [assignee]


def _ensure_known_anima(animas_dir: Path, anima_names: list[str], anima_name: str) -> None:
    if anima_name in set(anima_names) or (animas_dir / anima_name).is_dir():
        return
    raise HTTPException(status_code=404, detail={"error": "anima_not_found", "anima_name": anima_name})


def _history_truncated(store: TaskStore, owner: str | None, limit: int) -> bool:
    if limit <= 0:
        return False
    return _count_terminal_rows(store, owner) > limit


def _count_terminal_rows(store: TaskStore, owner: str | None) -> int:
    if not store.has_database:
        return 0
    with store.reader() as db:
        where = "WHERE json_extract(t.entry_json,'$.status') IN ('done','cancelled')"
        params: list = []
        if owner is not None:
            where += " AND t.anima=?"
            params.append(owner)
        return int(db.execute(f"SELECT COUNT(*) FROM tasks t {where}", params).fetchone()[0])


def _column_response(rows: list[BoardRow]) -> list[dict[str, Any]]:
    counts = {column.value: 0 for column in BoardColumn}
    for row in rows:
        counts[row.column.value] += 1
    return [
        {"id": column.value, "title": _COLUMN_TITLES[column], "count": counts[column.value]} for column in BoardColumn
    ]


def _count_corrupt_task_queue_lines(animas_dir: Path, anima_names: list[str]) -> int:
    from core.tasks.queue import TaskQueueManager

    return sum(
        TaskQueueManager(animas_dir / name, read_only=True).store.maintenance_status(name)["invalid_import_rows"]
        for name in anima_names
    )
