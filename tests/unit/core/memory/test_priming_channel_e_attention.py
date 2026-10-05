from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

from core.memory.priming import PrimingEngine
from core.tasks.queue import TaskQueueManager
from core.time_utils import now_local


@pytest.fixture
def anima_env(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    for subdir in ["episodes", "knowledge", "skills", "state"]:
        (anima_dir / subdir).mkdir(parents=True, exist_ok=True)
    return anima_dir


def _append_task_entry(
    anima_dir: Path,
    *,
    task_id: str,
    summary: str,
    updated_at: str,
    source: str = "human",
) -> None:
    queue_path = anima_dir / "state" / "task_queue.jsonl"
    entry = {
        "task_id": task_id,
        "ts": updated_at,
        "source": source,
        "original_instruction": summary,
        "assignee": anima_dir.name,
        "status": "pending",
        "summary": summary,
        "relay_chain": [],
        "updated_at": updated_at,
        "meta": {},
    }
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    from core.tasks.board.tasks import TaskStore, task_database_path

    TaskStore(task_database_path(anima_dir)).import_legacy(anima_dir)


@pytest.mark.asyncio
async def test_channel_e_surfaces_all_ledger_tasks(anima_env: Path) -> None:
    """All pending canonical tasks appear in Channel E."""
    anima_dir = anima_env
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
        original_instruction="other work",
        assignee="sakura",
        summary="other work",
        task_id="other1234",
    )

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "visible work" in result
    assert "other work" in result


@pytest.mark.asyncio
async def test_channel_e_surfaces_pending_tasks(anima_env: Path) -> None:
    """Pending tasks always appear regardless of any (now-removed) visibility."""
    anima_dir = anima_env
    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="pending work",
        assignee="sakura",
        summary="pending work",
        task_id="pending1234",
    )

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "pending work" in result


@pytest.mark.asyncio
async def test_channel_e_does_not_emit_ledger_missing_ids(anima_env: Path) -> None:
    """Regression (S17): an ID absent from the ledger must never surface."""
    anima_dir = anima_env
    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="will disappear",
        assignee="sakura",
        summary="will disappear",
        task_id="ghost1234",
    )
    with queue.store.transaction() as db:
        db.execute("DELETE FROM tasks WHERE anima='sakura' AND task_id='ghost1234'")

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "will disappear" not in result


@pytest.mark.asyncio
async def test_channel_e_task_results_freshness_only(anima_env: Path) -> None:
    """Channel E task_results gate is purely freshness-based."""
    anima_dir = anima_env
    results_dir = anima_dir / "state" / "task_results"
    results_dir.mkdir(parents=True)
    (results_dir / "hidden1234.md").write_text("hidden result", encoding="utf-8")
    (results_dir / "recent1234.md").write_text("recent result", encoding="utf-8")
    old_file = results_dir / "orphan1234.md"
    old_file.write_text("old orphan result", encoding="utf-8")
    old = (now_local() - timedelta(hours=25)).timestamp()
    os.utime(old_file, (old, old))

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "recent result" in result
    assert "hidden result" in result
    assert "old orphan result" not in result


@pytest.mark.asyncio
async def test_channel_e_preserves_legacy_prompt_signals(anima_env: Path) -> None:
    """STALE and auto-taskexec markers still surface (OVERDUE/deadline were retired)."""
    anima_dir = anima_env
    now = now_local()
    _append_task_entry(
        anima_dir,
        task_id="stale1234",
        summary="stale board work",
        updated_at=(now - timedelta(minutes=45)).isoformat(),
    )
    TaskQueueManager(anima_dir).add_task(
        source="anima",
        original_instruction="auto taskexec work",
        assignee="sakura",
        summary="auto taskexec work",
        task_id="auto1234",
        meta={"executor": "taskexec"},
        status="in_progress",
    )

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "stale board work" in result
    assert "STALE" in result
    assert "OVERDUE" not in result
    assert "(auto: TaskExec)" in result


@pytest.mark.asyncio
async def test_channel_e_preserves_delegated_status_section(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    subordinate_dir = data_dir / "animas" / "hinata"
    for directory in [anima_dir, subordinate_dir]:
        for subdir in ["episodes", "knowledge", "skills", "state"]:
            (directory / subdir).mkdir(parents=True, exist_ok=True)

    subordinate_task = TaskQueueManager(subordinate_dir).submit(
        {"task_id": "child1234", "title": "subordinate work", "description": "subordinate work"}
    )
    TaskQueueManager(anima_dir).store.alias("sakura", "delegated1234", "hinata", subordinate_task.task_id)

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert "subordinate work" in result  # alias reflects the canonical child record
    assert "hinata: pending" in result
    assert "⏳" in result


@pytest.mark.asyncio
async def test_channel_e_reads_sqlite_without_jsonl_projection(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    for subdir in ["episodes", "knowledge", "skills", "state"]:
        (anima_dir / subdir).mkdir(parents=True, exist_ok=True)

    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="fallback visible work",
        assignee="sakura",
        summary="fallback visible work",
        task_id="visible1234",
    )

    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()

    assert not (anima_dir / "state" / "task_queue.jsonl").exists()
    assert "fallback visible work" in result


@pytest.mark.asyncio
async def test_channel_e_reads_only_current_completed_attempt_result(tmp_path: Path):
    anima_dir = tmp_path / "runtime" / "animas" / "fixture"
    anima_dir.mkdir(parents=True)
    queue = TaskQueueManager(anima_dir)
    queue.submit({"task_id": "job", "title": "job", "description": "work"})
    attempt = queue.store.claim("fixture", "job", {"pid": 1, "process_start_time": 1})
    token = attempt["_attempt_token"]
    queue.store.finish(token, status="done", stop_kind="completed")
    result_dir = anima_dir / "state/task_results/job"
    result_dir.mkdir(parents=True)
    (result_dir / f"{token}.md").write_text("current completed result")
    (result_dir / "obsolete.md").write_text("stale result must not return")
    result = await PrimingEngine(anima_dir)._channel_e_pending_tasks()
    assert "[job] current completed result" in result
    assert "stale result" not in result
