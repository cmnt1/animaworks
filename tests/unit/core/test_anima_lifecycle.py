"""Unit tests for LifecycleMixin cron command zombie prevention."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
        mock_proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_shell", return_value=mock_proc),
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

        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_awaited()

    @pytest.mark.asyncio
    async def test_cron_command_skips_reap_on_completed_process(self):
        """When process completes normally, the finally block does not kill/wait again."""
        stub = self._make_anima_stub()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with (
            patch("asyncio.create_subprocess_shell", return_value=mock_proc),
            patch("core.tooling.handler.active_session_type") as mock_ast,
            patch("core.execution.session_context.RuntimeSessionContext.create") as create_runtime_context,
        ):
            mock_ast.reset = MagicMock()
            from core.anima.lifecycle import LifecycleMixin

            result = await LifecycleMixin.run_cron_command(
                stub,
                task_name="test-task",
                command="echo hello",
            )

        assert create_runtime_context.call_args.kwargs["thread_id"] == "cron-test-task"
        mock_proc.kill.assert_not_called()
        assert result["exit_code"] == 0
