from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory.task_queue import TaskQueueManager
from core.supervisor.task_retry import TaskRetryError, retry_task


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    path = tmp_path / "animas" / "sakura"
    (path / "state").mkdir(parents=True)
    return path


def test_retry_task_regenerates_pending_json_from_task_desc(anima_dir: Path):
    manager = TaskQueueManager(anima_dir)
    entry = manager.add_task(
        source="anima",
        original_instruction="Reflect Obsidian changes",
        assignee="sakura",
        summary="Obsidian reflection",
        deadline="1h",
        meta={
            "task_desc": {
                "task_type": "llm",
                "title": "Original title",
                "description": "Original description",
                "context": "Existing context",
                "working_directory": "E:\\OneDriveBiz\\Obsidian",
                "reply_to": "sakura",
                "source": "delegation",
            }
        },
    )
    manager.update_status(entry.task_id, "blocked", summary="BLOCKED: policy blocked")

    retried = retry_task(anima_dir, entry.task_id, summary="retry queued", submitted_by="sakura")

    assert retried.status == "in_progress"
    assert retried.meta["retry_count"] == 1

    pending_path = anima_dir / "state" / "pending" / f"{entry.task_id}.json"
    assert pending_path.exists()
    payload = json.loads(pending_path.read_text(encoding="utf-8"))
    assert payload["task_id"] == entry.task_id
    assert payload["title"] == "Original title"
    assert payload["description"] == "Original description"
    assert payload["context"] == "Existing context"
    assert payload["working_directory"] == "E:\\OneDriveBiz\\Obsidian"
    assert payload["submitted_by"] == "sakura"


def test_retry_task_can_fallback_to_queue_instruction(anima_dir: Path):
    manager = TaskQueueManager(anima_dir)
    entry = manager.add_task(
        source="anima",
        original_instruction="Retry from queue only",
        assignee="sakura",
        summary="Fallback retry",
        deadline="1h",
    )
    manager.update_status(entry.task_id, "blocked", summary="BLOCKED: read-only")

    retry_task(anima_dir, entry.task_id, submitted_by="sakura")

    pending_path = anima_dir / "state" / "pending" / f"{entry.task_id}.json"
    payload = json.loads(pending_path.read_text(encoding="utf-8"))
    assert payload["title"] == "Retry from queue only"
    assert payload["description"] == "Retry from queue only"


def test_retry_task_respects_retry_limit(anima_dir: Path):
    manager = TaskQueueManager(anima_dir)
    entry = manager.add_task(
        source="anima",
        original_instruction="Too many retries",
        assignee="sakura",
        summary="Retry limited",
        deadline="1h",
        meta={"retry_count": 3},
    )

    with pytest.raises(TaskRetryError, match="could not be regenerated"):
        retry_task(anima_dir, entry.task_id, submitted_by="sakura")
