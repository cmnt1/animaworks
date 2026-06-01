# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for TaskExec false-completion fixes (GH #145).

Covers:
- Bug A: cancelled/expired sentinel → correct queue status
- Bug B: error chunk detection → TaskExecError
- Bug B+: retry_start resets had_error
- Bug C: serial batch failed_dependency → queue sync
- _classify_task_result helper
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory.task_queue import TaskQueueManager
from core.supervisor.pending_executor import (
    _SENTINEL_CANCELLED,
    _SENTINEL_EXPIRED,
    PendingTaskExecutor,
    TaskExecError,
    _classify_task_result,
    _classify_task_result_for_desc,
)

# ── Helpers ──────────────────────────────────────────────


def _make_executor(tmp_path: Path) -> PendingTaskExecutor:
    anima_dir = tmp_path / "animas" / "test-anima"
    anima_dir.mkdir(parents=True, exist_ok=True)
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)
    mock_anima = MagicMock()
    mock_anima.agent.background_manager = MagicMock()
    mock_anima._background_lock = asyncio.Lock()
    mock_anima._status_slots = {"background": "idle"}
    mock_anima._task_slots = {"background": ""}
    mock_anima._active_parallel_tasks = {}
    return PendingTaskExecutor(
        anima=mock_anima,
        anima_name="test-anima",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


def _make_task_desc(**overrides) -> dict:
    base = {
        "task_id": "test-task-1",
        "title": "Test Task",
        "description": "Do something",
        "context": "",
        "acceptance_criteria": [],
        "constraints": [],
        "file_paths": [],
        "reply_to": None,
        "submitted_by": "unit-test",
        "submitted_at": "",
    }
    base.update(overrides)
    return base


async def _fake_streaming(*chunks):
    """Create an async generator that yields the given chunks."""

    async def _stream(prompt, trigger, **kw):
        for c in chunks:
            yield c

    return _stream


# ── _classify_task_result ──────────────────────────────────


class TestClassifyTaskResult:
    def test_cancelled(self):
        status, summary = _classify_task_result(_SENTINEL_CANCELLED)
        assert status == "cancelled"
        assert "cancelled" in summary.lower()

    def test_expired(self):
        status, summary = _classify_task_result(_SENTINEL_EXPIRED)
        assert status == "cancelled"
        assert "expired" in summary.lower()

    def test_normal_result(self):
        status, summary = _classify_task_result("Task completed successfully")
        assert status == "done"
        assert summary == "Task completed successfully"

    def test_empty_result(self):
        status, summary = _classify_task_result("")
        assert status == "done"
        assert summary == ""

    def test_long_result_truncated(self):
        long_text = "x" * 500
        status, summary = _classify_task_result(long_text)
        assert status == "done"
        assert len(summary) == 200

    def test_auth_failure_result_maps_to_failed(self):
        status, summary = _classify_task_result(
            'Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"Invalid authentication credentials"}}'
        )
        assert status == "failed"
        assert summary.startswith("FAILED: Failed to authenticate.")

    def test_synthesized_tool_errors_map_to_failed(self):
        status, summary = _classify_task_result(
            "(completed 27 tool call(s): Read, Bash, Grep...; errors=11)"
        )
        assert status == "failed"
        assert summary == "FAILED: Task produced no final response and reported 11 tool error(s)"

    def test_synthesized_tool_summary_without_errors_stays_done(self):
        status, summary = _classify_task_result(
            "(completed 3 tool call(s): Read, Bash, Grep)"
        )
        assert status == "done"
        assert summary == "(completed 3 tool call(s): Read, Bash, Grep)"

    def test_machine_handoff_start_log_maps_to_blocked(self):
        status, summary = _classify_task_result(
            "状況を把握しました。複数の修正が必要です。machineエージェントに委託して修正を進めます。まず関連ファイルを確認開始します。"
        )
        assert status == "blocked"
        assert summary.startswith("BLOCKED: Task reported only a machine handoff/start log")

    def test_unresolved_aff003_blocker_report_maps_to_blocked(self):
        status, summary = _classify_task_result(
            "Multiple unresolved problems remain:\n"
            "1. **108500/108502**: generated JSON body contains 4AXJKD+4BF3MA+5316\n"
            "2. **108501**: image URL 404 for IMG_20260530110659_011.jpg\n"
            "3. **108502**: public article images missing"
        )
        assert status == "blocked"
        assert "AFF-003 blockers" in summary

    def test_policy_blocked_partial_completion_maps_to_blocked(self):
        status, summary = _classify_task_result(
            "Review judgment is complete. Remaining work is Obsidian reflection only, "
            "but the filesystem sandbox is read-only and Remove-Item was rejected: blocked by policy. "
            "The file operation remains not applied."
        )
        assert status == "blocked"
        assert summary.startswith("BLOCKED: Task reported unresolved blockers")


# ── Bug B: error chunk detection ──────────────────────────


    def test_multistage_intermediate_result_maps_to_blocked(self):
        status, summary = _classify_task_result_for_desc(
            "Situation cleanup complete. Mira artifact is missing, so I will proceed with "
            "option 2 and create an instruction file for the machine retry.",
            {"allow_multistage": True},
        )
        assert status == "blocked"
        assert summary.startswith("BLOCKED: Multi-stage task reported")

    def test_non_multistage_intermediate_result_keeps_default_done(self):
        status, summary = _classify_task_result_for_desc(
            "Situation cleanup complete. Follow-up is available if needed.",
            {"allow_multistage": False},
        )
        assert status == "done"
        assert summary.startswith("Situation cleanup complete")

    def test_explicit_followup_result_maps_to_blocked_without_multistage_flag(self):
        status, summary = _classify_task_result_for_desc(
            "全エンジンがexit 255。machineが使えないため、直接実行経路（PowerShell/Python）で対応します。"
            "Smoke test通過。次にID_Articles=111655の現在値を確認します。",
            {"allow_multistage": False},
        )
        assert status == "blocked"
        assert summary.startswith("BLOCKED: Task reported an explicit follow-up")

    def test_english_fix_script_start_result_maps_to_blocked_without_multistage_flag(self):
        status, summary = _classify_task_result_for_desc(
            "Now I understand the exact issues. Let me write the fix script:",
            {"allow_multistage": False},
        )
        assert status == "blocked"
        assert summary.startswith("BLOCKED: Task reported an explicit follow-up")

    def test_japanese_evidence_collection_start_result_maps_to_blocked(self):
        status, summary = _classify_task_result_for_desc(
            "状況を確認しました。miyuが22:08 JSTにタスク実行開始したところです。"
            "まずDB現状確認と公開URL確認を実施し、証跡を収集します。",
            {"allow_multistage": False},
        )
        assert status == "blocked"
        assert summary.startswith("BLOCKED: Task reported an explicit follow-up")


class TestBlockedAutoRetry:
    def test_multistage_blocked_task_is_requeued(self, tmp_path: Path):
        executor = _make_executor(tmp_path)
        manager = TaskQueueManager(executor._anima_dir)
        entry = manager.add_task(
            source="anima",
            original_instruction="Finish verifier",
            assignee="test-anima",
            summary="Verifier",
            task_id="retry-blocked",
            meta={
                "task_desc": {
                    "task_type": "llm",
                    "title": "Finish verifier",
                    "description": "Produce final evidence",
                    "allow_multistage": True,
                    "reply_to": "sakura",
                }
            },
        )
        manager.update_status(entry.task_id, "blocked", summary="BLOCKED: missing final evidence")

        retried = executor._auto_retry_blocked_llm_task(
            {
                "task_id": entry.task_id,
                "task_type": "llm",
                "allow_multistage": True,
                "submitted_by": "sakura",
            }
        )

        updated = manager.get_task_by_id(entry.task_id)
        assert retried is True
        assert updated is not None
        assert updated.status == "in_progress"
        assert updated.meta["retry_count"] == 1
        assert (executor._anima_dir / "state" / "pending" / f"{entry.task_id}.json").exists()

    def test_blocked_task_without_multistage_flag_is_not_requeued(self, tmp_path: Path):
        executor = _make_executor(tmp_path)
        manager = TaskQueueManager(executor._anima_dir)
        entry = manager.add_task(
            source="anima",
            original_instruction="Ask a human",
            assignee="test-anima",
            summary="Human blocked",
            task_id="human-blocked",
        )
        manager.update_status(entry.task_id, "blocked", summary="BLOCKED: waiting for user")

        retried = executor._auto_retry_blocked_llm_task({"task_id": entry.task_id, "task_type": "llm"})

        assert retried is False
        assert manager.get_task_by_id(entry.task_id).status == "blocked"
        assert not (executor._anima_dir / "state" / "pending" / f"{entry.task_id}.json").exists()

    def test_explicit_followup_blocked_task_is_requeued_without_multistage_flag(self, tmp_path: Path):
        executor = _make_executor(tmp_path)
        manager = TaskQueueManager(executor._anima_dir)
        entry = manager.add_task(
            source="anima",
            original_instruction="Finish verifier",
            assignee="test-anima",
            summary="Verifier",
            task_id="retry-followup",
            meta={
                "task_desc": {
                    "task_type": "llm",
                    "title": "Finish verifier",
                    "description": "Produce final evidence",
                    "allow_multistage": False,
                    "reply_to": "sakura",
                }
            },
        )
        manager.update_status(
            entry.task_id,
            "blocked",
            summary="BLOCKED: Task reported an explicit follow-up/start step, not final evidence",
        )

        retried = executor._auto_retry_blocked_llm_task(
            {
                "task_id": entry.task_id,
                "task_type": "llm",
                "allow_multistage": False,
                "submitted_by": "sakura",
            }
        )

        updated = manager.get_task_by_id(entry.task_id)
        assert retried is True
        assert updated is not None
        assert updated.status == "in_progress"
        assert updated.meta["retry_count"] == 1
        assert (executor._anima_dir / "state" / "pending" / f"{entry.task_id}.json").exists()


class TestRunLlmTaskErrorDetection:
    @pytest.mark.asyncio
    async def test_error_chunk_raises_taskexec_error(self, tmp_path):
        """error chunk in stream → TaskExecError raised."""
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        chunks = [
            {"type": "text_delta", "text": "partial output"},
            {"type": "error", "message": "Agent SDK timeout"},
            {"type": "cycle_done", "cycle_result": {"summary": "partial output"}},
        ]

        async def fake_stream(prompt, trigger, **kw):
            for c in chunks:
                yield c

        executor._anima.agent.run_cycle_streaming = fake_stream
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.agent.set_interrupt_event = MagicMock()

        with (
            patch("core.paths.load_prompt", return_value="prompt"),
            patch("core.memory.activity.ActivityLogger"),
            patch("core.memory.streaming_journal.StreamingJournal"),
            pytest.raises(TaskExecError, match="Agent SDK timeout"),
        ):
            await executor._run_llm_task(task)

    @pytest.mark.asyncio
    async def test_retry_start_resets_error(self, tmp_path):
        """error → retry_start → cycle_done should NOT raise."""
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        chunks = [
            {"type": "text_delta", "text": "start"},
            {"type": "error", "message": "transient error"},
            {"type": "retry_start", "retry": 1, "max_retries": 3},
            {"type": "text_delta", "text": "recovered output"},
            {"type": "cycle_done", "cycle_result": {"summary": "recovered output"}},
        ]

        async def fake_stream(prompt, trigger, **kw):
            for c in chunks:
                yield c

        executor._anima.agent.run_cycle_streaming = fake_stream
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.agent.set_interrupt_event = MagicMock()

        with patch("core.paths.load_prompt", return_value="prompt"), \
             patch("core.memory.activity.ActivityLogger"), \
             patch("core.memory.streaming_journal.StreamingJournal"):
            result = await executor._run_llm_task(task)
            assert "recovered" in result

    @pytest.mark.asyncio
    async def test_normal_cycle_no_error(self, tmp_path):
        """Normal stream without error chunks → returns summary."""
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        chunks = [
            {"type": "text_delta", "text": "all good"},
            {"type": "cycle_done", "cycle_result": {"summary": "all good"}},
        ]

        async def fake_stream(prompt, trigger, **kw):
            for c in chunks:
                yield c

        executor._anima.agent.run_cycle_streaming = fake_stream
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.agent.set_interrupt_event = MagicMock()

        with patch("core.paths.load_prompt", return_value="prompt"), \
             patch("core.memory.activity.ActivityLogger"), \
             patch("core.memory.streaming_journal.StreamingJournal"):
            result = await executor._run_llm_task(task)
            assert result == "all good"

    @pytest.mark.asyncio
    async def test_auth_failure_summary_raises_taskexec_error(self, tmp_path):
        """Auth failure text in cycle summary should be treated as a failed task."""
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        chunks = [
            {
                "type": "cycle_done",
                "cycle_result": {
                    "summary": 'Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"Invalid authentication credentials"}}',
                },
            },
        ]

        async def fake_stream(prompt, trigger, **kw):
            for c in chunks:
                yield c

        executor._anima.agent.run_cycle_streaming = fake_stream
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.agent.set_interrupt_event = MagicMock()

        with (
            patch("core.paths.load_prompt", return_value="prompt"),
            patch("core.memory.activity.ActivityLogger"),
            patch("core.memory.streaming_journal.StreamingJournal"),
            pytest.raises(TaskExecError, match="Failed to authenticate"),
        ):
            await executor._run_llm_task(task)


# ── Bug A: cancelled/expired in _execute_llm_task ──────────


class TestExecuteLlmTaskStatusMapping:
    @pytest.mark.asyncio
    async def test_cancelled_maps_to_cancelled_status(self, tmp_path):
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        with patch.object(executor, "_run_llm_task", return_value=_SENTINEL_CANCELLED), \
             patch.object(executor, "_sync_task_queue") as mock_sync:
            await executor._execute_llm_task(task)
            assert mock_sync.call_args_list[0].args == ("test-task-1", "in_progress")
            assert mock_sync.call_args_list[-1].args == ("test-task-1", "cancelled")
            assert mock_sync.call_args_list[-1].kwargs["summary"] == "cancelled before execution"

    @pytest.mark.asyncio
    async def test_expired_maps_to_cancelled_status(self, tmp_path):
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        with patch.object(executor, "_run_llm_task", return_value=_SENTINEL_EXPIRED), \
             patch.object(executor, "_sync_task_queue") as mock_sync:
            await executor._execute_llm_task(task)
            assert mock_sync.call_args_list[0].args == ("test-task-1", "in_progress")
            assert mock_sync.call_args_list[-1].args == ("test-task-1", "cancelled")
            assert mock_sync.call_args_list[-1].kwargs["summary"] == "expired (TTL exceeded)"

    @pytest.mark.asyncio
    async def test_normal_result_maps_to_done(self, tmp_path):
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        with patch.object(executor, "_run_llm_task", return_value="success"), \
             patch.object(executor, "_sync_task_queue") as mock_sync:
            await executor._execute_llm_task(task)
            assert mock_sync.call_args_list[0].args == ("test-task-1", "in_progress")
            assert mock_sync.call_args_list[-1].args == ("test-task-1", "done")
            assert mock_sync.call_args_list[-1].kwargs["summary"] == "success"

    @pytest.mark.asyncio
    async def test_auth_failure_result_maps_to_failed(self, tmp_path):
        executor = _make_executor(tmp_path)
        task = _make_task_desc()
        auth_text = (
            'Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"Invalid authentication credentials"}}'
        )

        with patch.object(executor, "_run_llm_task", return_value=auth_text), \
             patch.object(executor, "_sync_task_queue") as mock_sync:
            await executor._execute_llm_task(task)
            assert mock_sync.call_args_list[0].args == ("test-task-1", "in_progress")
            assert mock_sync.call_args_list[-1].args[1] == "failed"
            assert mock_sync.call_args_list[-1].kwargs["summary"].startswith("FAILED: Failed to authenticate.")

    @pytest.mark.asyncio
    async def test_error_exception_maps_to_failed(self, tmp_path):
        executor = _make_executor(tmp_path)
        task = _make_task_desc()

        with patch.object(
            executor, "_run_llm_task", side_effect=TaskExecError("boom")
        ), patch.object(executor, "_sync_task_queue") as mock_sync, \
             patch.object(executor, "_write_failed_result"):
            await executor._execute_llm_task(task)
            assert mock_sync.call_args_list[0].args == ("test-task-1", "in_progress")
            assert mock_sync.call_args_list[-1].args[1] == "failed"


# ── Bug C: serial batch failed_dependency queue sync ────────


class TestSerialBatchFailedDependency:
    @pytest.mark.asyncio
    async def test_failed_dependency_syncs_to_queue(self, tmp_path):
        """Serial batch failed_dependency should call _sync_task_queue with 'failed'."""
        executor = _make_executor(tmp_path)

        tasks = [
            {"task_id": "dep1", "description": "dep", "depends_on": [], "parallel": False},
            {"task_id": "child1", "description": "child", "depends_on": ["dep1"], "parallel": False},
        ]

        with patch.object(executor, "_run_llm_task", side_effect=RuntimeError("dep failed")), \
             patch.object(executor, "_sync_task_queue") as mock_sync, \
             patch.object(executor, "_write_failed_result"), \
             patch.object(executor, "_get_semaphore", return_value=asyncio.Lock()):
            await executor._dispatch_batch("test-batch", tasks)

            sync_calls = {call[0][0]: call[0][1] for call in mock_sync.call_args_list}
            assert "dep1" in sync_calls
            assert sync_calls["dep1"] == "failed"
            assert "child1" in sync_calls
            assert sync_calls["child1"] == "failed"
