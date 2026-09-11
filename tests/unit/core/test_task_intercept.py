"""Unit tests for Task tool intercept → pending LLM task conversion."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

# ── PreToolUse hook Task branch ──────────────────────────────


class TestPreToolHookTaskBranch:
    """Verify the PreToolUse hook intercepts the Task tool."""

    @pytest.fixture()
    def hook(self, tmp_path: Path):
        """Build a pre-tool hook for testing (supervisor mode)."""
        try:
            import claude_agent_sdk.types  # noqa: F401
        except ImportError:
            pytest.skip("claude_agent_sdk not installed")

        from core.execution.agent_sdk import _build_pre_tool_hook

        anima_dir = tmp_path / "animas" / "hook_test"
        anima_dir.mkdir(parents=True)
        (anima_dir / "state" / "pending").mkdir(parents=True)

        with patch("core.execution._sdk_hooks._cache_subordinate_paths", return_value=([], [], [], [], [])):
            return _build_pre_tool_hook(anima_dir, has_subordinates=True)

    @pytest.fixture()
    def hook_with_callback(self, tmp_path: Path):
        """Build a pre-tool hook with on_task_intercepted callback (supervisor mode)."""
        try:
            import claude_agent_sdk.types  # noqa: F401
        except ImportError:
            pytest.skip("claude_agent_sdk not installed")

        from core.execution.agent_sdk import _build_pre_tool_hook

        anima_dir = tmp_path / "animas" / "hook_cb_test"
        anima_dir.mkdir(parents=True)
        (anima_dir / "state" / "pending").mkdir(parents=True)

        callback = MagicMock()

        with patch("core.execution._sdk_hooks._cache_subordinate_paths", return_value=([], [], [], [], [])):
            hook_fn = _build_pre_tool_hook(anima_dir, on_task_intercepted=callback, has_subordinates=True)

        return hook_fn, callback, anima_dir

    async def test_task_tool_hard_blocked(self, hook) -> None:
        """Task tool should be hard-blocked by the hook."""
        input_data = {
            "tool_name": "Task",
            "tool_input": {
                "description": "Do something",
                "prompt": "Full instructions here",
            },
        }

        with patch("core.execution._sdk_hooks._log_tool_use"):
            result = await hook(input_data, "tool-id-1", {})

        output = result.get("hookSpecificOutput", {})
        assert output.get("permissionDecision") == "deny"
        reason = output.get("permissionDecisionReason", "")
        assert "BLOCKED" in reason

    async def test_task_tool_no_pending_file(self, hook, tmp_path: Path) -> None:
        """Hard-blocked Task tool should NOT create pending files."""
        input_data = {
            "tool_name": "Task",
            "tool_input": {
                "description": "Background work",
                "prompt": "Do the work",
            },
        }

        with patch("core.execution._sdk_hooks._log_tool_use"):
            await hook(input_data, "tool-id-2", {})

        pending_dir = tmp_path / "animas" / "hook_test" / "state" / "pending"
        task_files = list(pending_dir.glob("*.json"))
        assert len(task_files) == 0

    async def test_callback_not_invoked_on_hard_block(self, hook_with_callback) -> None:
        """on_task_intercepted callback should NOT be called for hard-blocked tools."""
        hook_fn, callback, _ = hook_with_callback

        input_data = {
            "tool_name": "Task",
            "tool_input": {"description": "test", "prompt": "test"},
        }

        with patch("core.execution._sdk_hooks._log_tool_use"):
            await hook_fn(input_data, "tool-id-3", {})

        callback.assert_not_called()

    async def test_read_tool_unaffected(self, hook) -> None:
        """Non-Task tools should pass through normally."""
        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
        }

        with (
            patch("core.execution._sdk_hooks._log_tool_use"),
            patch("core.execution._sdk_hooks._check_a1_file_access", return_value=None),
            patch("core.execution._sdk_hooks._build_output_guard", return_value=None),
        ):
            result = await hook(input_data, "tool-id-4", {})

        output = result.get("hookSpecificOutput", {})
        assert output.get("permissionDecision") != "deny"

    async def test_bash_tool_unaffected(self, hook) -> None:
        """Bash tool should go through normal security checks, not Task intercept."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
        }

        with (
            patch("core.execution._sdk_hooks._log_tool_use"),
            patch("core.execution._sdk_hooks._check_a1_bash_command", return_value=None),
            patch("core.execution._sdk_hooks._build_output_guard", return_value=None),
        ):
            result = await hook(input_data, "tool-id-5", {})

        output = result.get("hookSpecificOutput", {})
        assert output.get("permissionDecision") != "deny"

    async def test_bash_violation_denied_with_trigger(self, hook) -> None:
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo safe; echo injected"},
        }

        with (
            patch("core.execution._sdk_hooks._log_tool_use") as log_tool,
            patch("core.execution._sdk_hooks._check_a1_bash_command", return_value="injection") as check,
            patch("core.execution._sdk_hooks._build_output_guard", return_value=None),
        ):
            result = await hook(input_data, "tool-id-injection", {})

        output = result.get("hookSpecificOutput", {})
        assert output.get("permissionDecision") == "deny"
        assert output.get("permissionDecisionReason") == "injection"
        check.assert_called_once_with(
            "echo safe; echo injected",
            ANY,
            superuser=False,
            trigger="unknown",
        )
        assert log_tool.call_args.kwargs["blocked"] is True

    async def test_task_output_also_blocked(self, hook) -> None:
        """TaskOutput is also hard-blocked since Agent/Task are disabled."""
        out_input = {
            "tool_name": "TaskOutput",
            "tool_input": {"task_id": "fake-id", "block": False, "timeout": 5000},
        }
        with patch("core.execution._sdk_hooks._log_tool_use"):
            out_result = await hook(out_input, "tool-id-out", {})

        out = out_result.get("hookSpecificOutput", {})
        assert out.get("permissionDecision") == "deny"
        assert "BLOCKED" in out.get("permissionDecisionReason", "")
