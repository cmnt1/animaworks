# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for canonical task-attempt failure safety and notifications."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.messaging.messenger import Messenger
from core.tasks.pending_executor import PendingTaskExecutor

# ── Helpers ──────────────────────────────────────────────────


def _make_executor(tmp_path: Path) -> PendingTaskExecutor:
    """Create a PendingTaskExecutor with mocked anima."""
    anima_dir = tmp_path / "animas" / "test-anima"
    anima_dir.mkdir(parents=True, exist_ok=True)

    mock_anima = MagicMock()
    mock_anima.agent.background_manager = MagicMock()
    mock_anima._background_lock = asyncio.Lock()
    mock_anima._status_slots = {"background": "idle"}
    mock_anima._task_slots = {"background": ""}
    mock_anima.messenger = MagicMock()

    return PendingTaskExecutor(
        anima=mock_anima,
        anima_name="test-anima",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


def _stop_after_first(executor: PendingTaskExecutor):
    """Return a mock for asyncio.wait_for that stops the loop after one iteration."""

    async def _mock(coro, *, timeout):
        if hasattr(coro, "close"):
            coro.close()
        executor._shutdown_event.set()
        raise TimeoutError

    return _mock


# ── TestLLMCanonicalLifecycle ───────────────────────────────


class TestLLMCanonicalLifecycle:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome", ["done", "crash"])
    async def test_attempt_ends_without_destroying_input(self, tmp_path, outcome):
        from core.tasks.queue import TaskQueueManager

        executor = _make_executor(tmp_path)
        queue = TaskQueueManager(executor._anima_dir)
        payload = {"task_type": "llm", "task_id": "llm-1", "title": "test", "description": "complete input"}
        queue.submit(payload)

        async def execute(task_desc):
            if outcome == "crash":
                raise RuntimeError("LLM failure")
            queue.update_status(task_desc["task_id"], "done")

        executor.execute_pending_task = execute
        with patch("core.tasks.pending_executor.asyncio.wait_for", side_effect=_stop_after_first(executor)):
            await executor.watcher_loop()
        assert queue.get_task_by_id("llm-1").status == ("done" if outcome == "done" else "pending")
        assert queue.store.active_attempts("test-anima") == []
        assert queue.store.pending("test-anima") == []
        assert queue.store.get_input("test-anima", "llm-1") == payload
        assert not (executor._anima_dir / "state" / "pending").exists()
        if outcome == "crash":
            assert len(queue.store.wakeups("test-anima")) == 1


# ── TestExecuteLLMTaskFailureHandling ────────────────────────


class TestExecuteLLMTaskFailureHandling:
    """_execute_llm_task writes a result marker and notifies reply_to on error."""

    @pytest.mark.asyncio
    async def test_writes_result_marker(self, tmp_path: Path) -> None:
        """_execute_llm_task records the error as the task result on exception."""
        executor = _make_executor(tmp_path)

        with patch.object(executor, "_run_llm_task", side_effect=RuntimeError("boom")):
            task_desc = {"task_id": "fail-1", "description": "test task"}
            await executor._execute_llm_task(task_desc)

        result_path = executor._anima_dir / "state" / "task_results" / "fail-1.md"
        assert result_path.exists()
        assert "RuntimeError" in result_path.read_text()

    @pytest.mark.asyncio
    async def test_crash_returns_queue_entry_to_pending(self, tmp_path: Path) -> None:
        """A crashed run puts the ledger entry back to pending with a crash stamp."""
        from core.tasks.queue import TaskQueueManager

        executor = _make_executor(tmp_path)
        (executor._anima_dir / "state").mkdir(parents=True, exist_ok=True)
        queue = TaskQueueManager(executor._anima_dir)
        queue.add_task(
            source="anima",
            original_instruction="work",
            assignee="test-anima",
            summary="work",
            status="in_progress",
            task_id="crash-1",
        )

        with patch.object(executor, "_run_llm_task", side_effect=RuntimeError("boom")):
            await executor._execute_llm_task({"task_id": "crash-1", "description": "test task"})

        entry = queue.get_task_by_id("crash-1")
        assert entry.status == "pending"
        assert entry.meta["last_run_stop_kind"] == "crash"
        assert entry.meta["last_run_ended_at"]
        # Nothing is re-enqueued for the harness to pick up again.
        assert not list((executor._anima_dir / "state" / "pending").glob("*.json"))

    @pytest.mark.asyncio
    async def test_sends_reply_to_notification_dict(self, tmp_path: Path) -> None:
        """When reply_to is a dict with 'name', sends failure notification."""
        executor = _make_executor(tmp_path)

        with (
            patch.object(executor, "_run_llm_task", side_effect=RuntimeError("oops")),
            patch("core.i18n.t", return_value="failure msg"),
        ):
            task_desc = {
                "task_id": "fail-notify",
                "description": "failing task",
                "reply_to": {"name": "manager-anima", "content": "please notify"},
            }
            await executor._execute_llm_task(task_desc)

        executor._anima.messenger.send.assert_called_once()
        call_kwargs = executor._anima.messenger.send.call_args
        assert call_kwargs[1]["to"] == "manager-anima"

    @pytest.mark.asyncio
    async def test_sends_reply_to_notification_string(self, tmp_path: Path) -> None:
        """When reply_to is a string, uses it as the recipient."""
        executor = _make_executor(tmp_path)

        with (
            patch.object(executor, "_run_llm_task", side_effect=RuntimeError("oops")),
            patch("core.i18n.t", return_value="failure msg"),
        ):
            task_desc = {
                "task_id": "fail-str",
                "description": "task",
                "reply_to": "some-anima",
            }
            await executor._execute_llm_task(task_desc)

        executor._anima.messenger.send.assert_called_once()
        call_kwargs = executor._anima.messenger.send.call_args
        assert call_kwargs[1]["to"] == "some-anima"

    @pytest.mark.asyncio
    async def test_self_notification_without_reply_to(self, tmp_path: Path) -> None:
        """When no reply_to, sends the failure notification to self."""
        executor = _make_executor(tmp_path)

        with patch.object(executor, "_run_llm_task", side_effect=RuntimeError("fail")):
            task_desc = {"task_id": "fail-noreply", "description": "test"}
            await executor._execute_llm_task(task_desc)

        executor._anima.messenger.send.assert_called_once()
        assert executor._anima.messenger.send.call_args.kwargs["to"] == "test-anima"
        result_path = executor._anima_dir / "state" / "task_results" / "fail-noreply.md"
        assert result_path.exists()

    @pytest.mark.asyncio
    async def test_non_shutdown_cancel_records_durable_attention(self, tmp_path):
        from core.tasks.board.tasks import process_identity
        from core.tasks.queue import TaskQueueManager

        executor = _make_executor(tmp_path)
        queue = TaskQueueManager(executor._anima_dir)
        queue.submit(
            {
                "task_type": "llm",
                "task_id": "cancelled",
                "title": "Cancelled task",
                "description": "work",
                "reply_to": "manager-anima",
            }
        )
        claim = queue.store.claim("test-anima", "cancelled", process_identity())
        executor.execute_pending_task = AsyncMock(side_effect=asyncio.CancelledError)
        with pytest.raises(asyncio.CancelledError):
            await executor._execute_canonical_task(claim)
        assert queue.get_task_by_id("cancelled").status == "pending"
        assert len(queue.store.wakeups("test-anima")) == 1
        executor._deliver_task_wakeups(queue.store)
        assert any(call.kwargs["to"] == "manager-anima" for call in executor._anima.messenger.send.call_args_list)
        assert not (executor._anima_dir / "state" / "pending").exists()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("shutdown", [True, False])
    async def test_live_child_keeps_claim_until_proven_dead(self, tmp_path, shutdown):
        from core.tasks.queue import TaskQueueManager

        executor = _make_executor(tmp_path)
        queue = TaskQueueManager(executor._anima_dir)
        payload = {
            "task_type": "llm",
            "task_id": "shutdown",
            "title": "Restarted task",
            "description": "work",
            "context": "original",
        }
        queue.submit(payload)
        claim = queue.store.claim("test-anima", "shutdown", {"pid": 123456, "process_start_time": 1})
        executor.execute_pending_task = AsyncMock(side_effect=asyncio.CancelledError)
        if shutdown:
            executor._shutdown_event.set()
        with (
            patch("core.tasks.board.tasks.identity_liveness", return_value="live"),
            pytest.raises(asyncio.CancelledError),
        ):
            await executor._execute_canonical_task(claim)
        assert queue.get_task_by_id("shutdown").status == "in_progress"
        assert len(queue.store.active_attempts("test-anima")) == 1
        executor._anima.messenger.send.assert_not_called()
        with patch("core.tasks.board.tasks.identity_liveness", return_value="live"):
            executor._recover_task_attempts(queue.store)
        assert len(queue.store.active_attempts("test-anima")) == 1
        with patch("core.tasks.board.tasks.identity_liveness", return_value="dead"):
            executor._recover_task_attempts(queue.store)
        assert queue.get_task_by_id("shutdown").status == "pending"
        assert queue.store.pending("test-anima") == []
        assert queue.store.get_input("test-anima", "shutdown") == payload

    @pytest.mark.asyncio
    async def test_notification_failure_does_not_propagate(self, tmp_path: Path) -> None:
        """If messenger.send fails, the exception is swallowed."""
        executor = _make_executor(tmp_path)
        executor._anima.messenger.send.side_effect = ConnectionError("network error")

        with (
            patch.object(executor, "_run_llm_task", side_effect=RuntimeError("boom")),
            patch("core.i18n.t", return_value="msg"),
        ):
            task_desc = {
                "task_id": "fail-notif-err",
                "description": "task",
                "reply_to": {"name": "boss"},
            }
            await executor._execute_llm_task(task_desc)

        result_path = executor._anima_dir / "state" / "task_results" / "fail-notif-err.md"
        assert result_path.exists()

    @pytest.mark.asyncio
    async def test_status_slots_reset_on_failure(self, tmp_path: Path) -> None:
        """Status slots are reset to idle even on failure."""
        executor = _make_executor(tmp_path)

        with patch.object(executor, "_run_llm_task", side_effect=RuntimeError("err")):
            task_desc = {"task_id": "slot-test", "description": "test"}
            await executor._execute_llm_task(task_desc)

        assert executor._anima._status_slots["background"] == "idle"
        assert executor._anima._task_slots["background"] == ""

    @pytest.mark.asyncio
    async def test_completion_notification_can_be_self_addressed(self, tmp_path: Path) -> None:
        """Task completion notifications may target the submitting anima itself."""
        executor = _make_executor(tmp_path)
        shared_dir = tmp_path / "shared"
        executor._anima.messenger = Messenger(shared_dir, "test-anima")

        async def _run_cycle_streaming(*_args, **_kwargs):
            yield {
                "type": "cycle_done",
                "cycle_result": {"summary": "task finished", "action": "responded"},
            }

        executor._anima.agent.run_cycle_streaming = _run_cycle_streaming
        task_desc = {
            "task_id": "self-complete",
            "title": "Self completion",
            "description": "notify the submitter",
            "reply_to": "test-anima",
        }

        result = await executor._run_llm_task(task_desc)

        assert result == "task finished"
        inbox_files = list((shared_dir / "inbox" / "test-anima").glob("*.json"))
        assert len(inbox_files) == 1
        delivered = json.loads(inbox_files[0].read_text(encoding="utf-8"))
        assert delivered["from_person"] == "test-anima"
        assert delivered["to_person"] == "test-anima"
        assert "self-complete" in delivered["content"]


# ── TestI18nTemplate ─────────────────────────────────────────


class TestI18nTemplate:
    """Verify task_fail_notify i18n template exists and formats correctly."""

    def test_ja_template(self) -> None:
        from core.i18n import t

        result = t(
            "pending_executor.task_fail_notify",
            locale="ja",
            task_id="test-123",
            title="テストタスク",
            error="RuntimeError: boom",
        )
        assert "test-123" in result
        assert "テストタスク" in result
        assert "RuntimeError: boom" in result
        assert "元の入力は保存" in result

    def test_en_template(self) -> None:
        from core.i18n import t

        result = t(
            "pending_executor.task_fail_notify",
            locale="en",
            task_id="test-456",
            title="Test Task",
            error="ValueError: bad",
        )
        assert "test-456" in result
        assert "Test Task" in result
        assert "ValueError: bad" in result
        assert "Original input is retained" in result

    def test_ko_template(self) -> None:
        from core.i18n import t

        result = t(
            "pending_executor.task_fail_notify",
            locale="ko",
            task_id="test-789",
            title="테스트 작업",
            error="RuntimeError: 실패",
        )
        assert "test-789" in result
        assert "테스트 작업" in result
        assert "원래 입력은 보존" in result
