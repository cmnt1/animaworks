"""Tests for Agent/Task tool interception in _sdk_hooks.py.

Verifies:
  - Both "Agent" and "Task" tool names are intercepted
  - Non-supervisor path writes to state/pending/ (not SDK native)
  - Supervisor path delegates to subordinate or falls back to pending
  - reply_to is set to anima_dir.name in intercepted tasks
  - "TaskOutput" and "AgentOutput" are handled for intercepted tasks
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.execution._sdk_hooks import (
    _intercept_task_to_pending,
)

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "ayame"
    d.mkdir(parents=True)
    (d / "state").mkdir()
    return d


# ── _intercept_task_to_pending ────────────────────────────────


class TestInterceptTaskToPending:
    def test_writes_pending_json(self, anima_dir: Path):
        tool_input = {
            "description": "Background research",
            "prompt": "Search for information",
        }
        task_id = _intercept_task_to_pending(anima_dir, tool_input, "tu_001")

        pending_dir = anima_dir / "state" / "pending"
        task_file = pending_dir / f"{task_id}.json"
        assert task_file.exists()

        data = json.loads(task_file.read_text(encoding="utf-8"))
        assert data["task_type"] == "llm"
        assert data["task_id"] == task_id
        assert data["title"] == "Background research"
        assert data["description"] == "Search for information"
        assert data["submitted_by"] == "self_task_intercept"

    def test_reply_to_set_to_anima_name(self, anima_dir: Path):
        """reply_to should be the anima directory name."""
        tool_input = {"description": "test", "prompt": "test"}
        task_id = _intercept_task_to_pending(anima_dir, tool_input, "tu_002")

        task_file = anima_dir / "state" / "pending" / f"{task_id}.json"
        data = json.loads(task_file.read_text(encoding="utf-8"))
        assert data["reply_to"] == "ayame"

    def test_returns_task_id(self, anima_dir: Path):
        tool_input = {"description": "test", "prompt": "test"}
        task_id = _intercept_task_to_pending(anima_dir, tool_input, "tu_003")
        assert isinstance(task_id, str)
        assert len(task_id) == 12

    def test_context_from_state_files(self, anima_dir: Path):
        """Context should include current_state.md content."""
        (anima_dir / "state" / "current_state.md").write_text(
            "Working on API refactor",
            encoding="utf-8",
        )
        tool_input = {"description": "related task", "prompt": "do stuff"}
        task_id = _intercept_task_to_pending(anima_dir, tool_input, "tu_004")

        task_file = anima_dir / "state" / "pending" / f"{task_id}.json"
        data = json.loads(task_file.read_text(encoding="utf-8"))
        assert "API refactor" in data["context"]


# ── PreToolUse hook: Agent/Task interception ──────────────────


class TestPreToolHookAgentIntercept:
    """Test the PreToolUse hook catches both 'Agent' and 'Task' tool names."""

    def _build_hook(self, anima_dir: Path, *, has_subordinates: bool = False):
        """Build the pre-tool hook with mock SDK types."""
        from core.execution._sdk_hooks import _build_pre_tool_hook

        return _build_pre_tool_hook(
            anima_dir,
            has_subordinates=has_subordinates,
        )

    @pytest.mark.asyncio
    async def test_agent_tool_intercepted_non_supervisor(self, anima_dir: Path):
        """'Agent' tool should be intercepted for non-supervisor animas."""
        hook = self._build_hook(anima_dir, has_subordinates=False)

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Agent",
            "tool_input": {
                "description": "Research task",
                "prompt": "Find information about X",
            },
        }
        result = await hook(input_data, "tu_agent_01", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "INTERCEPT_OK" in output["permissionDecisionReason"]

        pending_files = list((anima_dir / "state" / "pending").glob("*.json"))
        assert len(pending_files) == 1

    @pytest.mark.asyncio
    async def test_task_tool_intercepted_non_supervisor(self, anima_dir: Path):
        """'Task' tool should also be intercepted for non-supervisor animas."""
        hook = self._build_hook(anima_dir, has_subordinates=False)

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Task",
            "tool_input": {
                "description": "Build task",
                "prompt": "Compile the project",
            },
        }
        result = await hook(input_data, "tu_task_01", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "INTERCEPT_OK" in output["permissionDecisionReason"]

    @pytest.mark.asyncio
    async def test_agent_tool_intercepted_supervisor_fallback(self, anima_dir: Path):
        """'Agent' tool for supervisor falls back to pending when no subordinates available."""
        hook = self._build_hook(anima_dir, has_subordinates=True)

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Agent",
            "tool_input": {
                "description": "Delegate task",
                "prompt": "Do something important",
            },
        }
        result = await hook(input_data, "tu_agent_02", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "INTERCEPT_OK" in output["permissionDecisionReason"]

    @pytest.mark.asyncio
    async def test_agent_output_intercepted(self, anima_dir: Path):
        """'AgentOutput' for intercepted tasks should return INTERCEPT_OK."""
        hook = self._build_hook(anima_dir, has_subordinates=False)

        mock_context = MagicMock()

        input_data = {
            "tool_name": "Agent",
            "tool_input": {
                "description": "test task",
                "prompt": "do stuff",
            },
        }
        await hook(input_data, "tu_agent_03", mock_context)

        pending_files = list((anima_dir / "state" / "pending").glob("*.json"))
        task_id = pending_files[0].stem

        output_input = {
            "tool_name": "AgentOutput",
            "tool_input": {"task_id": task_id},
        }
        result = await hook(output_input, "tu_output_01", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "INTERCEPT_OK" in output["permissionDecisionReason"]

    @pytest.mark.asyncio
    async def test_task_output_intercepted(self, anima_dir: Path):
        """'TaskOutput' for intercepted tasks should also return INTERCEPT_OK."""
        hook = self._build_hook(anima_dir, has_subordinates=False)

        mock_context = MagicMock()

        input_data = {
            "tool_name": "Task",
            "tool_input": {
                "description": "test",
                "prompt": "test",
            },
        }
        await hook(input_data, "tu_task_02", mock_context)

        pending_files = list((anima_dir / "state" / "pending").glob("*.json"))
        task_id = pending_files[0].stem

        output_input = {
            "tool_name": "TaskOutput",
            "tool_input": {"task_id": task_id},
        }
        result = await hook(output_input, "tu_output_02", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_non_intercepted_task_output_passes_through(self, anima_dir: Path):
        """TaskOutput for a non-intercepted task_id should pass through."""
        hook = self._build_hook(anima_dir, has_subordinates=False)

        mock_context = MagicMock()
        output_input = {
            "tool_name": "TaskOutput",
            "tool_input": {"task_id": "unknown_task_id"},
        }
        result = await hook(output_input, "tu_output_03", mock_context)

        output = result.get("hookSpecificOutput")
        if output is not None:
            assert output.get("permissionDecision") != "deny"

    @pytest.mark.asyncio
    async def test_on_task_intercepted_callback(self, anima_dir: Path):
        """The on_task_intercepted callback should fire when Agent is intercepted."""
        callback_called = []

        from core.execution._sdk_hooks import _build_pre_tool_hook

        hook = _build_pre_tool_hook(
            anima_dir,
            has_subordinates=False,
            on_task_intercepted=lambda: callback_called.append(True),
        )

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Agent",
            "tool_input": {"description": "test", "prompt": "test"},
        }
        await hook(input_data, "tu_cb_01", mock_context)

        assert len(callback_called) == 1

    def _build_hook_with_trigger(self, anima_dir: Path, trigger: str):
        """Build hook with a session_stats dict containing a trigger."""
        from core.execution._sdk_hooks import _build_pre_tool_hook

        return _build_pre_tool_hook(
            anima_dir,
            has_subordinates=False,
            session_stats={
                "tool_call_count": 0,
                "total_result_bytes": 0,
                "system_prompt_tokens": 100,
                "user_prompt_tokens": 50,
                "force_chain": False,
                "trigger": trigger,
                "start_time": 0.0,
                "hb_soft_warned": False,
                "hb_soft_timeout": 300,
            },
        )

    @pytest.mark.asyncio
    async def test_agent_blocked_in_taskexec(self, anima_dir: Path):
        """Agent tool should be blocked (not intercepted) from TaskExec sessions."""
        hook = self._build_hook_with_trigger(anima_dir, "task:abc123")

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Agent",
            "tool_input": {"description": "sub-research", "prompt": "find X"},
        }
        result = await hook(input_data, "tu_taskexec_01", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "BLOCKED" in output["permissionDecisionReason"]
        assert "INTERCEPT_OK" not in output["permissionDecisionReason"]

        pending_files = list((anima_dir / "state" / "pending").glob("*.json"))
        assert len(pending_files) == 0, "No pending task should be written"

    @pytest.mark.asyncio
    async def test_task_blocked_in_taskexec(self, anima_dir: Path):
        """Task tool should be blocked from TaskExec sessions."""
        hook = self._build_hook_with_trigger(anima_dir, "task:def456")

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Task",
            "tool_input": {"description": "sub-task", "prompt": "do Y"},
        }
        result = await hook(input_data, "tu_taskexec_02", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "BLOCKED" in output["permissionDecisionReason"]

    @pytest.mark.asyncio
    async def test_agent_allowed_in_chat(self, anima_dir: Path):
        """Agent tool should be intercepted (not blocked) from chat sessions."""
        hook = self._build_hook_with_trigger(anima_dir, "chat")

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Agent",
            "tool_input": {"description": "research", "prompt": "find Z"},
        }
        result = await hook(input_data, "tu_chat_01", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "INTERCEPT_OK" in output["permissionDecisionReason"]

        pending_files = list((anima_dir / "state" / "pending").glob("*.json"))
        assert len(pending_files) == 1

    @pytest.mark.asyncio
    async def test_read_tool_not_intercepted(self, anima_dir: Path):
        """Non-Agent/Task tools should pass through normally."""
        hook = self._build_hook(anima_dir, has_subordinates=False)

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": str(anima_dir / "identity.md")},
        }
        result = await hook(input_data, "tu_read_01", mock_context)

        output = result.get("hookSpecificOutput")
        if output is not None:
            assert output.get("permissionDecision") != "deny"


# ── PreToolUse hook: submit_tasks intercept deny reason ─────────────────


class TestSubmitTasksInterceptDenyReason:
    """Test submit_tasks intercept returns improved deny reason to prevent duplicate delegation."""

    def _build_hook(self, anima_dir: Path, *, has_subordinates: bool = False, session_stats: dict | None = None):
        from core.execution._sdk_hooks import _build_pre_tool_hook

        return _build_pre_tool_hook(
            anima_dir,
            has_subordinates=has_subordinates,
            session_stats=session_stats,
        )

    @pytest.mark.asyncio
    async def test_submit_tasks_intercept_success_reason(self, anima_dir: Path):
        """Success case: deny reason starts with SUCCESS, warns about DUPLICATE."""
        success_result = json.dumps(
            {
                "status": "submitted",
                "batch_id": "test",
                "task_count": 2,
                "task_ids": ["t1", "t2"],
                "message": "Batch submitted",
            },
            ensure_ascii=False,
        )

        with patch(
            "core.tooling.handler_skills.SkillsToolsMixin._handle_submit_tasks",
            return_value=success_result,
        ):
            hook = self._build_hook(anima_dir, has_subordinates=False)
            mock_context = MagicMock()
            input_data = {
                "tool_name": "submit_tasks",
                "tool_input": {
                    "batch_id": "test",
                    "tasks": [
                        {"task_id": "t1", "title": "T1", "description": "D1"},
                        {"task_id": "t2", "title": "T2", "description": "D2"},
                    ],
                },
            }
            result = await hook(input_data, "tu_001", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        reason = output["permissionDecisionReason"]
        assert reason.startswith("SUCCESS")
        assert "DUPLICATE" in reason
        assert "re-submit" in reason.lower() or "Do NOT" in reason

    @pytest.mark.asyncio
    async def test_submit_tasks_intercept_error_reason(self, anima_dir: Path):
        """Error case: deny reason does NOT start with SUCCESS, contains error."""
        error_result = json.dumps(
            {
                "status": "error",
                "error_type": "InvalidArguments",
                "message": "batch_id is required",
            },
            ensure_ascii=False,
        )

        with patch(
            "core.tooling.handler_skills.SkillsToolsMixin._handle_submit_tasks",
            return_value=error_result,
        ):
            hook = self._build_hook(anima_dir, has_subordinates=False)
            mock_context = MagicMock()
            input_data = {
                "tool_name": "submit_tasks",
                "tool_input": {"batch_id": "", "tasks": []},
            }
            result = await hook(input_data, "tu_002", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        reason = output["permissionDecisionReason"]
        assert not reason.startswith("SUCCESS")
        assert "error" in reason.lower()

    @pytest.mark.asyncio
    async def test_submit_tasks_blocked_in_taskexec(self, anima_dir: Path):
        """submit_tasks should be blocked from TaskExec sessions."""
        hook = self._build_hook(
            anima_dir,
            session_stats={
                "tool_call_count": 0,
                "total_result_bytes": 0,
                "system_prompt_tokens": 100,
                "user_prompt_tokens": 50,
                "force_chain": False,
                "trigger": "task:xyz789",
                "start_time": 0.0,
                "hb_soft_warned": False,
                "hb_soft_timeout": 300,
            },
        )

        mock_context = MagicMock()
        input_data = {
            "tool_name": "submit_tasks",
            "tool_input": {
                "batch_id": "test",
                "tasks": [{"task_id": "t1", "title": "T1", "description": "D1"}],
            },
        }
        result = await hook(input_data, "tu_st_taskexec", mock_context)

        output = result.get("hookSpecificOutput")
        assert output is not None
        assert output["permissionDecision"] == "deny"
        assert "BLOCKED" in output["permissionDecisionReason"]
