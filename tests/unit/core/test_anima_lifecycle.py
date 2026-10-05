"""Unit tests for LifecycleMixin cron command zombie prevention."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import sys
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import psutil
import pytest


@pytest.mark.asyncio
async def test_project_daily_consolidation_skips_phase_a_and_scopes_prompt() -> None:
    from core.anima.lifecycle import LifecycleMixin
    from core.schemas import CycleResult, ModelConfig

    owner = SimpleNamespace(
        name="librarian",
        memory=MagicMock(),
        _agent_session_lock=asyncio.Lock(),
        _run_autonomous_skill_learning=lambda: None,
    )
    owner.memory.read_model_config.return_value = ModelConfig(model="test-model")
    agent = MagicMock()
    agent.run_cycle = AsyncMock(return_value=CycleResult(trigger="consolidation:daily", action="completed"))
    owner.agent = agent

    engine = MagicMock()
    engine.project = "foo"
    engine.previous_local_day_window.return_value = (date(2026, 8, 12), MagicMock(), MagicMock())
    engine._collect_recent_episodes.return_value = [
        {"date": "2026-08-12", "time": "13:00", "content": "Project update"}
    ]
    engine._find_merge_candidates.return_value = []

    cfg = SimpleNamespace(
        consolidation=SimpleNamespace(llm_model="test-model", llm_credential=None),
    )
    with (
        patch("core.config.load_config", return_value=cfg),
        patch("core.anima.lifecycle.load_prompt", return_value="base prompt"),
        patch(
            "core.anima.lifecycle._consolidation_model_config",
            return_value=ModelConfig(model="test-model"),
        ),
    ):
        await LifecycleMixin._run_daily_consolidation(owner, engine)

    engine.collect_activity_chunks.assert_not_called()
    engine._collect_recent_episodes.assert_called_once_with(hours=24)
    prompt = agent.run_cycle.await_args.args[0]
    assert "episodes/projects/foo/" in prompt
    assert "knowledge/projects/foo/" in prompt
    assert agent.run_cycle.await_args.kwargs["thread_id"] == "consolidation-daily"


@pytest.mark.asyncio
async def test_cron_tasks_use_distinct_sanitized_session_threads() -> None:
    from core.anima.lifecycle import LifecycleMixin
    from core.schemas import CycleResult, ModelConfig

    agent = MagicMock()
    agent.model_config = ModelConfig(model="test-model")
    agent.run_cycle = AsyncMock(return_value=CycleResult(trigger="cron", action="completed", summary="ok"))
    agent._tool_handler.set_active_session_type.return_value = "session-token"
    owner = SimpleNamespace(
        name="cron-test",
        _background_lock=asyncio.Lock(),
        _status_slots={"background": "idle"},
        _task_slots={"background": ""},
        _get_interrupt_event=lambda _name: asyncio.Event(),
        _mark_busy_start=MagicMock(),
        _keepalive_while_busy=AsyncMock(),
        _build_cron_prompt=MagicMock(return_value="cron prompt"),
        _agent_for_lane=lambda _lane: agent,
        _agent_session_context=lambda _lane: asyncio.Lock(),
        _resolve_background_config=lambda _name: None,
        _activity=MagicMock(),
        memory=MagicMock(),
        _enforce_state_size_limit=MagicMock(),
        _notify_lock_released=MagicMock(),
        _last_activity=None,
    )
    owner._activity.alog = AsyncMock()
    owner.memory.read_model_config.return_value = agent.model_config
    owner.memory.append_cron_log = MagicMock()

    async def keepalive() -> None:
        await asyncio.Event().wait()

    owner._keepalive_while_busy = keepalive
    with patch("core.tooling.handler.active_session_type") as active_session_type:
        active_session_type.reset = MagicMock()
        await LifecycleMixin.run_cron_task(owner, "daily report", "first task")
        await LifecycleMixin.run_cron_task(owner, "weekly/report", "second task")

    thread_ids = [call.kwargs["thread_id"] for call in agent.run_cycle.await_args_list]
    assert thread_ids == ["cron-daily_report", "cron-weekly_report"]


class TestRunCronCommandZombieReap:
    """Tests for run_cron_command() reaping subprocess on CancelledError."""

    def _make_anima_stub(self):
        """Build a minimal LifecycleMixin-compatible stub."""
        from core.anima.lifecycle import LifecycleMixin

        stub = MagicMock(spec=LifecycleMixin)
        stub.name = "test-anima"
        stub._background_lock = asyncio.Lock()
        stub._mark_busy_start = MagicMock()
        stub._status_slots = {"background": "idle"}
        stub._task_slots = {"background": ""}
        stub._notify_lock_released = MagicMock()
        stub._last_activity = None

        mock_handler = MagicMock()
        mock_handler.set_active_session_type = MagicMock(return_value="token")
        mock_handler.set_session_origin = MagicMock()
        stub.agent = MagicMock()
        stub.agent._tool_handler = mock_handler

        stub.memory = MagicMock()
        stub._activity = MagicMock()
        stub._activity.alog = AsyncMock()

        return stub

    @pytest.mark.asyncio
    async def test_cron_command_reaps_on_cancellation(self):
        """When CancelledError interrupts communicate(), the subprocess is killed and waited."""
        stub = self._make_anima_stub()

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.pid = 12345
        mock_proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_shell", return_value=mock_proc),
            patch("core.anima.lifecycle.snapshot_descendants", return_value=[]),
            patch("core.anima.lifecycle.kill_tree" if __import__("os").name == "nt" else "core.anima.lifecycle.signal_tree") as kill_group,
            patch("core.tooling.handler.active_session_type") as mock_ast,
        ):
            mock_ast.reset = MagicMock()
            from core.anima.lifecycle import LifecycleMixin

            try:
                await LifecycleMixin.run_cron_command(
                    stub,
                    task_name="test-task",
                    command="echo hello",
                )
            except (asyncio.CancelledError, Exception):
                pass

        kill_group.assert_called_once()
        assert kill_group.call_args.args[0] == 12345
        if __import__("os").name != "nt":
            assert kill_group.call_args.args[1] == signal.SIGKILL
        mock_proc.wait.assert_awaited()

    @pytest.mark.asyncio
    async def test_cron_command_skips_reap_on_completed_process(self):
        """When process completes normally, the finally block does not kill/wait again."""
        stub = self._make_anima_stub()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with (
            patch("asyncio.create_subprocess_shell", return_value=mock_proc) as create_shell,
            patch("core.tooling.handler.active_session_type") as mock_ast,
            patch("core.execution.session.session_context.RuntimeSessionContext.create") as create_runtime_context,
        ):
            mock_ast.reset = MagicMock()
            from core.anima.lifecycle import LifecycleMixin

            result = await LifecycleMixin.run_cron_command(
                stub,
                task_name="test-task",
                command="echo hello",
                env={"ANIMAWORKS_ANIMA_DIR": "/animas/test"},
            )

        create_shell.assert_awaited_once()
        shell_kwargs = create_shell.await_args.kwargs
        assert shell_kwargs["env"] == {"ANIMAWORKS_ANIMA_DIR": "/animas/test"}
        assert "cwd" not in shell_kwargs
        assert create_runtime_context.call_args.kwargs["thread_id"] == "cron-test-task"
        mock_proc.wait.assert_not_awaited()
        assert result["exit_code"] == 0
        stub.memory.append_cron_command_log.assert_called_once()
        activity_call = stub._activity.alog.await_args
        assert activity_call.args[0] == "cron_executed"
        assert activity_call.kwargs["meta"] == {
            "task_name": "test-task",
            "exit_code": 0,
            "command": "echo hello",
            "tool": "",
        }

    @pytest.mark.asyncio
    async def test_root_cron_commands_can_overlap_without_shared_lock(self):
        """Direct root commands retain the old per-runner parallelism."""
        from core.anima.lifecycle import LifecycleMixin

        stub = self._make_anima_stub()
        both_started = asyncio.Event()
        release = asyncio.Event()
        started_count = 0

        async def communicate():
            nonlocal started_count
            started_count += 1
            if started_count == 2:
                both_started.set()
            await release.wait()
            return b"", b""

        processes = []
        for pid in (12345, 12346):
            proc = AsyncMock()
            proc.returncode = 0
            proc.pid = pid
            proc.communicate = AsyncMock(side_effect=communicate)
            proc.wait = AsyncMock()
            processes.append(proc)
        process_iter = iter(processes)

        async def create_process(*_args, **_kwargs):
            return next(process_iter)

        with (
            patch("asyncio.create_subprocess_shell", side_effect=create_process),
            patch("core.tooling.handler.active_session_type") as mock_ast,
        ):
            mock_ast.reset = MagicMock()
            tasks = [
                asyncio.create_task(
                    LifecycleMixin.run_cron_command(
                        stub,
                        task_name=f"task-{index}",
                        command="true",
                        serialize=False,
                    )
                )
                for index in range(2)
            ]
            try:
                await asyncio.wait_for(both_started.wait(), timeout=1)
                overlapped = True
            except TimeoutError:
                overlapped = False
            finally:
                release.set()
            await asyncio.gather(*tasks)

        assert overlapped
        assert not stub._background_lock.locked()
        assert not stub._active_cron_commands

    @pytest.mark.asyncio
    @pytest.mark.skipif(os.name != "posix", reason="process groups")
    async def test_cron_command_timeout_kills_the_entire_process_group(self, tmp_path, monkeypatch):
        """A timed-out shell command and its child processes are killed together."""
        from core.anima import lifecycle
        from core.anima.lifecycle import LifecycleMixin

        stub = self._make_anima_stub()
        child_pid_path = tmp_path / "child.pid"
        child_code = (
            "import subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
            f"open({str(child_pid_path)!r},'w').write(str(child.pid)); "
            "time.sleep(30)"
        )
        command = shlex.join([sys.executable, "-c", child_code])
        monkeypatch.setattr(lifecycle, "_CRON_COMMAND_TIMEOUT_SECONDS", 0.25)

        with patch("core.tooling.handler.active_session_type") as mock_ast:
            mock_ast.reset = MagicMock()
            result = await LifecycleMixin.run_cron_command(stub, task_name="timeout", command=command)

        assert result["exit_code"] == 1
        assert "exceeded 0.25s limit" in result["stderr"]
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                child = psutil.Process(child_pid)
                if child.status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.NoSuchProcess:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail(f"cron command child {child_pid} survived the process-group kill")

        stub.memory.append_cron_command_log.assert_called_once()
        assert stub.memory.append_cron_command_log.call_args.kwargs["exit_code"] == 1
        activity_call = stub._activity.alog.await_args
        assert activity_call.args[0] == "cron_executed"
        assert activity_call.kwargs["meta"]["exit_code"] == 1
