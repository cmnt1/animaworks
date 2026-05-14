from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest

from core.memory.priming import PrimingEngine
from core.memory.task_queue import TaskQueueManager
from core.taskboard.store import TaskBoardStore
from core.time_utils import now_local


@pytest.fixture
def attention_env(tmp_path: Path) -> tuple[Path, TaskBoardStore]:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    for subdir in ["episodes", "knowledge", "skills", "state"]:
        (anima_dir / subdir).mkdir(parents=True, exist_ok=True)
    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    return anima_dir, store


@pytest.mark.asyncio
async def test_channel_e_filters_suppressed_tasks(attention_env: tuple[Path, TaskBoardStore]) -> None:
    anima_dir, store = attention_env
    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="visible work",
        assignee="sakura",
        summary="visible work",
        task_id="visible1234",
    )
    queue.add_task(
        source="human",
        original_instruction="archived work",
        assignee="sakura",
        summary="archived work",
        task_id="hidden1234",
    )
    store.upsert_metadata(anima_name="sakura", task_id="hidden1234", visibility="archived")

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "visible work" in result
    assert "archived work" not in result


@pytest.mark.asyncio
async def test_channel_e_filters_snoozed_tasks(attention_env: tuple[Path, TaskBoardStore]) -> None:
    anima_dir, store = attention_env
    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="snoozed work",
        assignee="sakura",
        summary="snoozed work",
        task_id="snoozed1234",
    )
    store.upsert_metadata(
        anima_name="sakura",
        task_id="snoozed1234",
        visibility="snoozed",
        snoozed_until=(now_local() + timedelta(hours=2)).isoformat(),
    )

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "snoozed work" not in result


@pytest.mark.asyncio
async def test_channel_e_filters_task_results(attention_env: tuple[Path, TaskBoardStore]) -> None:
    anima_dir, store = attention_env
    results_dir = anima_dir / "state" / "task_results"
    results_dir.mkdir(parents=True)
    (results_dir / "hidden1234.md").write_text("hidden result", encoding="utf-8")
    (results_dir / "recent1234.md").write_text("recent result", encoding="utf-8")
    old_file = results_dir / "orphan1234.md"
    old_file.write_text("old orphan result", encoding="utf-8")
    old = (now_local() - timedelta(hours=25)).timestamp()
    os.utime(old_file, (old, old))
    store.upsert_metadata(anima_name="sakura", task_id="hidden1234", visibility="tombstoned")

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "recent result" in result
    assert "hidden result" not in result
    assert "old orphan result" not in result


@pytest.mark.asyncio
async def test_channel_e_falls_back_when_taskboard_db_is_corrupt(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    for subdir in ["episodes", "knowledge", "skills", "state"]:
        (anima_dir / subdir).mkdir(parents=True, exist_ok=True)
    shared_dir = data_dir / "shared"
    shared_dir.mkdir()
    (shared_dir / "taskboard.sqlite3").write_text("not sqlite", encoding="utf-8")

    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="fallback visible work",
        assignee="sakura",
        summary="fallback visible work",
        task_id="visible1234",
    )

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "fallback visible work" in result
