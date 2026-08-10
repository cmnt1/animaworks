from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import TaskPersistenceError
from core.memory.task_queue import TaskQueueManager
from core.supervisor.pending_executor import PendingTaskExecutor


def _make_executor(tmp_path: Path) -> PendingTaskExecutor:
    anima_dir = tmp_path / "animas" / "test-anima"
    (anima_dir / "state").mkdir(parents=True)
    anima = MagicMock()
    anima._background_lock = asyncio.Lock()
    anima._status_slots = {"background": "idle"}
    anima._task_slots = {"background": ""}
    anima._active_parallel_tasks = {}
    anima._active_background_workers = {}
    anima.agent.run_cycle_streaming = _successful_stream
    anima.agent.reset_reply_tracking = MagicMock()
    anima.agent.reset_read_paths = MagicMock()
    anima.agent.set_task_cwd = MagicMock()
    anima.agent.set_interrupt_event = MagicMock()
    return PendingTaskExecutor(
        anima=anima,
        anima_name="test-anima",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


async def _successful_stream(*_args, **_kwargs):
    yield {"type": "text_delta", "text": "finished output"}
    yield {
        "type": "cycle_done",
        "cycle_result": {
            "summary": "finished",
            "action": "complete",
            "tool_call_records": [
                {"tool_name": "run_command", "input_summary": "pytest -q"},
            ],
        },
    }


def _task(task_id: str, **overrides) -> dict:
    task = {
        "task_type": "llm",
        "task_id": task_id,
        "title": "Completion test",
        "description": "finish the task",
        "context": "original context",
        "reply_to": None,
        "submitted_at": "",
    }
    task.update(overrides)
    return task


def _queue_task(executor: PendingTaskExecutor, task_id: str) -> TaskQueueManager:
    manager = TaskQueueManager(executor._anima_dir)
    manager.add_task(
        source="anima",
        original_instruction="finish the task",
        assignee="test-anima",
        summary="completion test",
        task_id=task_id,
        status="in_progress",
    )
    return manager


@pytest.mark.asyncio
async def test_agent_declaration_allows_done(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "declared")
    manager.update_meta(
        "declared",
        {"completed_by": "agent_declaration", "result_note": "verified result"},
    )

    with (
        patch("core.paths.load_prompt", return_value="prompt"),
        patch("core.memory.activity.ActivityLogger"),
        patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True),
    ):
        await executor._execute_llm_task(_task("declared"))

    entry = manager.get_task_by_id("declared")
    assert entry is not None
    assert entry.status == "done"
    assert entry.summary == "verified result"


@pytest.mark.asyncio
async def test_missing_declaration_reenqueues_checkpoint_without_notification(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "continued")
    executor._anima.messenger.send = MagicMock()

    with (
        patch("core.paths.load_prompt", return_value="prompt"),
        patch("core.memory.activity.ActivityLogger") as activity,
        patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True),
    ):
        await executor._execute_llm_task(_task("continued", reply_to="supervisor"))

    pending = json.loads(
        (executor._anima_dir / "state" / "pending" / "continued.json").read_text(encoding="utf-8")
    )
    assert pending["continuation_count"] == 1
    assert "前回実行のcheckpoint" in pending["context"]
    assert "finished output" in pending["context"]
    assert "run_command: pytest -q" in pending["context"]
    assert manager.get_task_by_id("continued").status == "in_progress"
    executor._anima.messenger.send.assert_not_called()
    assert activity.return_value.log.call_args_list[-1].kwargs["meta"]["status"] == "continued"


@pytest.mark.asyncio
async def test_missing_declaration_at_limit_marks_task_failed(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "limit")

    with (
        patch("core.paths.load_prompt", return_value="prompt"),
        patch("core.memory.activity.ActivityLogger"),
        patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True),
    ):
        await executor._execute_llm_task(_task("limit", continuation_count=3))

    entry = manager.get_task_by_id("limit")
    assert entry is not None
    assert entry.status == "failed"
    assert "TaskExecError" in entry.summary
    assert "after 3 continuations" in entry.summary


@pytest.mark.asyncio
async def test_declaration_gate_can_be_disabled(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "legacy")

    with (
        patch("core.paths.load_prompt", return_value="prompt"),
        patch("core.memory.activity.ActivityLogger"),
        patch("core.supervisor.pending_executor._completion_declaration_required", return_value=False),
    ):
        await executor._execute_llm_task(_task("legacy"))

    assert manager.get_task_by_id("legacy").status == "done"


def test_recover_processing_continues_below_limit_and_fails_at_limit(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "recoverable")
    _queue_task(executor, "exhausted")
    processing = executor._anima_dir / "state" / "pending" / "processing"
    failed = executor._anima_dir / "state" / "pending" / "failed"
    processing.mkdir(parents=True)
    failed.mkdir()
    (processing / "recoverable.json").write_text(
        json.dumps(_task("recoverable", continuation_count=0)),
        encoding="utf-8",
    )
    (processing / "exhausted.json").write_text(
        json.dumps(_task("exhausted", continuation_count=3)),
        encoding="utf-8",
    )

    with patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True):
        PendingTaskExecutor._recover_processing(processing, failed, executor._anima_dir)

    resumed = json.loads(
        (executor._anima_dir / "state" / "pending" / "recoverable.json").read_text(encoding="utf-8")
    )
    assert resumed["continuation_count"] == 1
    assert "プロセス異常終了" in resumed["context"]
    assert manager.get_task_by_id("recoverable").status == "in_progress"
    assert (failed / "exhausted.json").exists()
    assert manager.get_task_by_id("exhausted").status == "failed"


def test_recover_processing_preserves_existing_continuation(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "already-pending")
    pending = executor._anima_dir / "state" / "pending"
    processing = pending / "processing"
    failed = pending / "failed"
    processing.mkdir(parents=True)
    failed.mkdir()
    existing = _task("already-pending", continuation_count=1, context="new checkpoint")
    (pending / "already-pending.json").write_text(json.dumps(existing), encoding="utf-8")
    (processing / "already-pending.json").write_text(
        json.dumps(_task("already-pending", context="stale processing")),
        encoding="utf-8",
    )

    with patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True):
        PendingTaskExecutor._recover_processing(processing, failed, executor._anima_dir)

    preserved = json.loads((pending / "already-pending.json").read_text(encoding="utf-8"))
    assert preserved["context"] == "new checkpoint"
    assert not (processing / "already-pending.json").exists()


def test_update_task_done_records_declaration_and_result(tmp_path: Path) -> None:
    from core.memory import MemoryManager
    from core.tooling.handler import ToolHandler

    anima_dir = tmp_path / "animas" / "test-anima"
    for directory in ("state", "episodes", "knowledge", "procedures", "skills"):
        (anima_dir / directory).mkdir(parents=True, exist_ok=True)
    handler = ToolHandler(anima_dir, MemoryManager(anima_dir))
    manager = TaskQueueManager(anima_dir)
    entry = manager.add_task(
        source="anima",
        original_instruction="work",
        assignee="test-anima",
        summary="work",
    )

    result = json.loads(
        handler.handle(
            "update_task",
            {"task_id": entry.task_id, "status": "done", "result": "tests passed"},
        )
    )

    assert result["status"] == "done"
    assert result["summary"] == "tests passed"
    assert result["meta"]["completed_by"] == "agent_declaration"
    assert result["meta"]["declared_at"]
    assert result["meta"]["result_note"] == "tests passed"


def test_update_task_done_uses_server_fallback_on_read_only_queue(tmp_path: Path) -> None:
    from core.memory import MemoryManager
    from core.tooling.handler import ToolHandler

    anima_dir = tmp_path / "animas" / "test-anima"
    for directory in ("state", "episodes", "knowledge", "procedures", "skills"):
        (anima_dir / directory).mkdir(parents=True, exist_ok=True)
    handler = ToolHandler(anima_dir, MemoryManager(anima_dir))
    manager = TaskQueueManager(anima_dir)
    entry = manager.add_task(
        source="anima",
        original_instruction="work",
        assignee="test-anima",
        summary="work",
    )
    fallback_task = entry.model_copy(
        update={
            "status": "done",
            "summary": "done remotely",
            "meta": {"completed_by": "agent_declaration", "result_note": "done remotely"},
        }
    ).model_dump(mode="json")

    with (
        patch(
            "core.memory.task_queue.TaskQueueManager.update_meta",
            side_effect=TaskPersistenceError("Read-only file system"),
        ),
        patch.object(
            handler,
            "_persist_task_update_via_server",
            return_value=(fallback_task, None),
        ) as fallback,
    ):
        result = json.loads(
            handler.handle(
                "update_task",
                {"task_id": entry.task_id, "status": "done", "result": "done remotely"},
            )
        )

    assert result["status"] == "done"
    assert fallback.call_args.kwargs["meta"]["completed_by"] == "agent_declaration"


def test_recovered_streaming_journal_is_added_to_checkpoint(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "journal")
    processing = executor._anima_dir / "state" / "pending" / "processing"
    processing.mkdir(parents=True)
    descriptor = processing / "journal.json"
    descriptor.write_text(json.dumps(_task("journal")), encoding="utf-8")

    with patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True):
        assert executor.add_recovered_task_checkpoint(
            "journal",
            "recovered partial output",
            [{"tool": "run_command", "args_summary": "git status"}],
        )

    recovered = json.loads(descriptor.read_text(encoding="utf-8"))
    assert "recovered partial output" in recovered["context"]
    assert "run_command: git status" in recovered["context"]


def test_should_defer_claim_while_prior_attempt_finishing(tmp_path: Path) -> None:
    """Continuation re-enqueue must not be claimed while the old attempt cleans up."""
    executor = _make_executor(tmp_path)
    pending_dir = executor._anima_dir / "state" / "pending"
    processing_dir = pending_dir / "processing"
    processing_dir.mkdir(parents=True, exist_ok=True)
    pending_path = pending_dir / "aaaa11112222.json"  # canonical: stem == task_id
    pending_path.write_text('{"task_id": "aaaa11112222", "task_type": "llm"}')
    desc = {"task_id": "aaaa11112222", "task_type": "llm"}

    # Case 1: old attempt still registered in _active_task_ids
    executor._active_task_ids.add("aaaa11112222")
    assert executor._should_defer_claim(pending_path, desc, processing_dir) is True

    # Case 2: id released but old processing descriptor not yet unlinked
    executor._active_task_ids.discard("aaaa11112222")
    (processing_dir / "aaaa11112222.json").write_text("{}")
    assert executor._should_defer_claim(pending_path, desc, processing_dir) is True

    # Case 3: fully cleaned up -> claimable
    (processing_dir / "aaaa11112222.json").unlink()
    assert executor._should_defer_claim(pending_path, desc, processing_dir) is False


def test_should_defer_claim_ignores_non_canonical_duplicates(tmp_path: Path) -> None:
    """Genuine duplicates (different filename, same task_id) still get quarantined."""
    executor = _make_executor(tmp_path)
    pending_dir = executor._anima_dir / "state" / "pending"
    processing_dir = pending_dir / "processing"
    processing_dir.mkdir(parents=True, exist_ok=True)
    dup_path = pending_dir / "second.json"
    dup_path.write_text('{"task_id": "aaaa11112222", "task_type": "llm"}')
    executor._active_task_ids.add("aaaa11112222")
    desc = {"task_id": "aaaa11112222", "task_type": "llm"}
    assert executor._should_defer_claim(dup_path, desc, processing_dir) is False


def test_reenqueue_backoff_delays_second_and_later_continuations(tmp_path: Path) -> None:
    import time

    executor = _make_executor(tmp_path)
    pending_dir = executor._anima_dir / "state" / "pending"

    executor._reenqueue_with_checkpoint(_task("backoff"), "output", [])
    first = json.loads((pending_dir / "backoff.json").read_text(encoding="utf-8"))
    assert first["continuation_count"] == 1
    assert "continuation_not_before" not in first

    executor._reenqueue_with_checkpoint(first, "output", [])
    second = json.loads((pending_dir / "backoff.json").read_text(encoding="utf-8"))
    assert second["continuation_count"] == 2
    assert second["continuation_not_before"] == pytest.approx(time.time() + 180.0, abs=5.0)


def test_should_defer_claim_respects_backoff(tmp_path: Path) -> None:
    import time

    executor = _make_executor(tmp_path)
    pending_dir = executor._anima_dir / "state" / "pending"
    processing_dir = pending_dir / "processing"
    processing_dir.mkdir(parents=True, exist_ok=True)
    pending_path = pending_dir / "backoff2.json"
    desc = {"task_id": "backoff2", "task_type": "llm", "continuation_not_before": time.time() + 60}
    pending_path.write_text(json.dumps(desc))
    assert executor._should_defer_claim(pending_path, desc, processing_dir) is True

    desc["continuation_not_before"] = time.time() - 1
    assert executor._should_defer_claim(pending_path, desc, processing_dir) is False


@pytest.mark.asyncio
async def test_blocked_declaration_stops_continuation(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "stuck")
    manager.update_status("stuck", "blocked", summary="waiting on repo permission")
    executor._anima.messenger.send = MagicMock()

    with (
        patch("core.paths.load_prompt", return_value="prompt"),
        patch("core.memory.activity.ActivityLogger"),
        patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True),
    ):
        await executor._execute_llm_task(_task("stuck"))

    entry = manager.get_task_by_id("stuck")
    assert entry is not None
    assert entry.status == "blocked"
    assert not (executor._anima_dir / "state" / "pending" / "stuck.json").exists()
    executor._anima.messenger.send.assert_not_called()
