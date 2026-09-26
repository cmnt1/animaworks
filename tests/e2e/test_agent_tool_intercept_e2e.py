"""E2E tests for Agent/Task tool hard-block flow.

Verifies the full pipeline:
  1. PreToolUse hook hard-blocks "Agent" / "Task" tool (no pending creation)
  3. _tool_summary handles "Agent" tool
  5. AgentOutput / TaskOutput are also blocked
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def anima_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir) / "animas" / "ayame"
        for sub in [
            "episodes",
            "knowledge",
            "skills",
            "state",
            "state/pending",
            "state/task_results",
        ]:
            (d / sub).mkdir(parents=True)
        yield d


class TestAgentToolHardBlockE2E:
    """Full pipeline: Agent tool → hard block → no pending file."""

    def test_tool_summary_handles_agent(self):
        """_tool_summary generates detail for both Agent and Task tools."""
        from core.execution._tool_summary import make_tool_detail_chunk

        agent_chunk = make_tool_detail_chunk(
            "Agent",
            "tool_1",
            {"description": "Research task"},
        )
        assert agent_chunk is not None
        assert agent_chunk["detail"] == "Research task"
        assert agent_chunk["tool_name"] == "Agent"

        task_chunk = make_tool_detail_chunk(
            "Task",
            "tool_2",
            {"description": "Build task"},
        )
        assert task_chunk is not None
        assert task_chunk["detail"] == "Build task"

    @pytest.mark.asyncio
    async def test_hook_hard_blocks_agent_no_pending(self, anima_dir: Path):
        """Full hook flow: Agent tool → hard-blocked → NO pending file."""
        from core.execution._sdk_hooks import _build_pre_tool_hook

        hook = _build_pre_tool_hook(
            anima_dir,
            has_subordinates=False,
        )

        mock_context = MagicMock()
        input_data = {
            "tool_name": "Agent",
            "tool_input": {
                "description": "Background analysis",
                "prompt": "Analyze the codebase structure",
            },
        }

        result = await hook(input_data, "tu_e2e_002", mock_context)

        output = result.get("hookSpecificOutput")
        assert output["permissionDecision"] == "deny"
        assert "BLOCKED" in output["permissionDecisionReason"]
        assert "submit_tasks" not in output["permissionDecisionReason"]

        pending_files = list((anima_dir / "state" / "pending").glob("*.json"))
        assert len(pending_files) == 0

    @pytest.mark.asyncio
    async def test_agent_output_blocked(self, anima_dir: Path):
        """AgentOutput is blocked (Agent/Task disabled)."""
        from core.execution._sdk_hooks import _build_pre_tool_hook

        hook = _build_pre_tool_hook(
            anima_dir,
            has_subordinates=False,
        )

        mock_context = MagicMock()

        agent_output_input = {
            "tool_name": "AgentOutput",
            "tool_input": {"task_id": "any_task_id"},
        }
        result = await hook(agent_output_input, "tu_e2e_004", mock_context)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "BLOCKED" in result["hookSpecificOutput"]["permissionDecisionReason"]

    @pytest.mark.asyncio
    async def test_task_output_blocked(self, anima_dir: Path):
        """TaskOutput is blocked."""
        from core.execution._sdk_hooks import _build_pre_tool_hook

        hook = _build_pre_tool_hook(
            anima_dir,
            has_subordinates=False,
        )

        mock_context = MagicMock()
        task_output_input = {
            "tool_name": "TaskOutput",
            "tool_input": {"task_id": "any_task_id"},
        }
        result = await hook(task_output_input, "tu_e2e_005", mock_context)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestBypassPermissionsConfig:
    """Verify _build_sdk_options uses bypassPermissions mode."""

    def test_bypass_permissions_mode(self):
        """The _build_sdk_options should set permission_mode to bypassPermissions."""
        from tests.helpers.mocks import patch_agent_sdk

        with patch_agent_sdk():
            from core.execution.agent_sdk import AgentSDKExecutor
            from core.schemas import ModelConfig

            config = ModelConfig(
                model="claude-sonnet-4-6",
                api_key="sk-test",
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                ad = Path(tmpdir) / "animas" / "test"
                ad.mkdir(parents=True)

                executor = AgentSDKExecutor(
                    model_config=config,
                    anima_dir=ad,
                )

                session_stats = {
                    "tool_call_count": 0,
                    "total_result_bytes": 0,
                    "system_prompt_tokens": 100,
                    "user_prompt_tokens": 50,
                    "force_chain": False,
                }

                options, temp_files = executor._build_sdk_options(
                    "test prompt",
                    200000,
                    session_stats,
                )

                assert options.permission_mode == "bypassPermissions"
                for f in temp_files:
                    f.unlink(missing_ok=True)
