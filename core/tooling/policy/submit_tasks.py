from __future__ import annotations

"""Submit a validated task batch without depending on ``ToolHandler``."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("animaworks.tooling.submit_tasks")


def _error_result(error_type: str, message: str) -> str:
    return json.dumps(
        {
            "status": "error",
            "error_type": error_type,
            "message": message,
        },
        ensure_ascii=False,
    )


def submit_tasks(
    anima_dir: Path,
    anima_name: str,
    args: dict[str, Any],
    *,
    session_origin: str = "",
) -> str:
    """Validate and atomically publish a complete DAG task batch."""
    from core.tasks.dispatch import publish_tasks
    from core.tasks.wake import request_wake
    from core.time_utils import now_iso
    from core.trust import ORIGIN_HUMAN

    source = "human" if session_origin == ORIGIN_HUMAN else "anima"
    batch_id = args.get("batch_id", "")
    tasks = args.get("tasks", [])
    if not isinstance(batch_id, str) or not batch_id:
        return _error_result("InvalidArguments", "batch_id is required")
    if not isinstance(tasks, list) or not tasks or not all(isinstance(task, dict) for task in tasks):
        return _error_result("InvalidArguments", "tasks must contain at least one task")

    submitted_at = now_iso()
    payloads = [
        dict(task)
        if task.get("resume") is True
        else {
            "task_type": "llm",
            "task_id": task.get("task_id"),
            "batch_id": batch_id,
            "title": task.get("title"),
            "description": task.get("description"),
            "parallel": task.get("parallel", False),
            "depends_on": task.get("depends_on", []),
            "context": task.get("context", ""),
            "acceptance_criteria": task.get("acceptance_criteria", []),
            "constraints": task.get("constraints", []),
            "file_paths": task.get("file_paths", []),
            "submitted_by": anima_name,
            "submitted_at": submitted_at,
            "reply_to": task.get("reply_to", anima_name),
            "workspace": task.get("workspace", ""),
            "model": task.get("model", ""),
        }
        for task in tasks
    ]
    try:
        entries = publish_tasks(anima_dir, payloads, source=source)
    except ValueError as exc:
        return _error_result("InvalidArguments", str(exc))
    except Exception as exc:
        logger.exception("Failed to submit task batch %s", batch_id)
        return _error_result("PersistenceFailed", str(exc))

    request_wake(anima_dir.name)
    return json.dumps(
        {
            "status": "submitted",
            "batch_id": batch_id,
            "task_count": len(entries),
            "task_ids": [entry.task_id for entry in entries],
            "message": (
                f"Batch '{batch_id}' submitted with {len(entries)} tasks. "
                "Parallel tasks will execute concurrently. "
                "Tasks with depends_on will wait for dependencies."
            ),
        },
        ensure_ascii=False,
    )
