from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.priming import PrimingEngine
from core.memory.task_queue import TaskQueueManager
from core.taskboard.store import TaskBoardStore

pytestmark = pytest.mark.e2e


async def test_taskboard_attention_filters_channel_e_end_to_end(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    for subdir in ["episodes", "knowledge", "skills", "state"]:
        (anima_dir / subdir).mkdir(parents=True, exist_ok=True)

    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="ship visible work",
        assignee="sakura",
        summary="ship visible work",
        task_id="visible1234",
    )
    queue.add_task(
        source="human",
        original_instruction="do not resurface",
        assignee="sakura",
        summary="do not resurface",
        task_id="hidden1234",
    )

    results_dir = anima_dir / "state" / "task_results"
    results_dir.mkdir(parents=True)
    (results_dir / "hidden1234.md").write_text("hidden completed result", encoding="utf-8")
    (results_dir / "visible-result.md").write_text("fresh completed result", encoding="utf-8")

    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    store.upsert_metadata(anima_name="sakura", task_id="hidden1234", visibility="archived")

    output = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "ship visible work" in output
    assert "do not resurface" not in output
    assert "hidden completed result" not in output
    assert "fresh completed result" in output
