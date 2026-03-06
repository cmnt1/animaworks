from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.memory.task_queue — TaskQueueManager and task lifecycle."""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.memory.task_queue import (
    TaskPersistenceError,
    TaskQueueManager,
    _TERMINAL_STATUSES,
)


# ── Test 1: _append raises TaskPersistenceError on OSError ─────────────


def test_append_raises_task_persistence_error_on_oserror(tmp_path: Path) -> None:
    """Test that _append raises TaskPersistenceError when file write fails.

    Mock the file open to raise OSError, then verify TaskPersistenceError
    is raised. Test through add_task() which calls _append().
    """
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)

    tqm = TaskQueueManager(anima_dir)

    state_dir = anima_dir / "state"
    state_dir.chmod(0o444)
    try:
        with pytest.raises(TaskPersistenceError):
            tqm.add_task(
                source="human",
                original_instruction="test task",
                assignee="anima",
                summary="test",
                deadline="1h",
            )
    finally:
        state_dir.chmod(0o755)


# ── Test 2: "failed" status is valid ───────────────────────────────────


def test_update_status_failed_is_valid(tmp_path: Path) -> None:
    """Test that update_status("failed") works correctly.

    Create a task, update to "failed", verify it returns the entry
    with status="failed".
    """
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)

    tqm = TaskQueueManager(anima_dir)
    entry = tqm.add_task(
        source="human",
        original_instruction="test",
        assignee="anima",
        summary="test task",
        deadline="1h",
    )

    result = tqm.update_status(entry.task_id, "failed")
    assert result is not None
    assert result.status == "failed"
    assert result.task_id == entry.task_id


# ── Test 3: _TERMINAL_STATUSES and compact() ────────────────────────────


def test_compact_removes_terminal_statuses(tmp_path: Path) -> None:
    """Test that compact() removes "failed" tasks (along with "done" and "cancelled").

    Create tasks with various statuses, compact, verify only non-terminal remain.
    """
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)

    tqm = TaskQueueManager(anima_dir)

    e1 = tqm.add_task(
        source="human",
        original_instruction="task 1",
        assignee="anima",
        summary="pending",
        deadline="1h",
    )
    e2 = tqm.add_task(
        source="human",
        original_instruction="task 2",
        assignee="anima",
        summary="in progress",
        deadline="1h",
    )
    e3 = tqm.add_task(
        source="human",
        original_instruction="task 3",
        assignee="anima",
        summary="done",
        deadline="1h",
    )
    e4 = tqm.add_task(
        source="human",
        original_instruction="task 4",
        assignee="anima",
        summary="failed",
        deadline="1h",
    )
    e5 = tqm.add_task(
        source="human",
        original_instruction="task 5",
        assignee="anima",
        summary="cancelled",
        deadline="1h",
    )

    tqm.update_status(e3.task_id, "done")
    tqm.update_status(e4.task_id, "failed")
    tqm.update_status(e5.task_id, "cancelled")

    assert "failed" in _TERMINAL_STATUSES
    assert "done" in _TERMINAL_STATUSES
    assert "cancelled" in _TERMINAL_STATUSES

    removed = tqm.compact()

    assert removed == 3  # done, failed, cancelled
    remaining = tqm.list_tasks()
    remaining_ids = {t.task_id for t in remaining}
    assert e1.task_id in remaining_ids
    assert e2.task_id in remaining_ids
    assert e3.task_id not in remaining_ids
    assert e4.task_id not in remaining_ids
    assert e5.task_id not in remaining_ids


# ── Test 4: task_tracker filters "failed" correctly ─────────────────────


def test_task_tracker_completed_includes_failed(tmp_path: Path) -> None:
    """Test that task_tracker with status='completed' includes 'failed' tasks."""
    from unittest.mock import MagicMock

    from core.tooling.handler import ToolHandler

    animas_dir = tmp_path / "animas"
    sakura_dir = animas_dir / "sakura"
    hinata_dir = animas_dir / "hinata"
    sakura_dir.mkdir(parents=True)
    hinata_dir.mkdir(parents=True)
    (sakura_dir / "permissions.md").write_text("", encoding="utf-8")
    (sakura_dir / "state").mkdir(exist_ok=True)
    (hinata_dir / "state").mkdir(exist_ok=True)

    # Create delegated task in sakura's queue
    from core.memory.task_queue import TaskQueueManager

    sakura_tqm = TaskQueueManager(sakura_dir)
    hinata_tqm = TaskQueueManager(hinata_dir)

    hinata_task = hinata_tqm.add_task(
        source="human",
        original_instruction="subordinate task",
        assignee="hinata",
        summary="sub task",
        deadline="1h",
    )
    hinata_tqm.update_status(hinata_task.task_id, "failed")

    sakura_tqm.add_delegated_task(
        original_instruction="delegate to hinata",
        assignee="hinata",
        summary="delegated",
        deadline="1h",
        meta={"delegated_to": "hinata", "delegated_task_id": hinata_task.task_id},
    )

    memory = MagicMock()
    memory.read_permissions.return_value = ""

    from core.config.models import AnimaModelConfig

    mock_cfg = MagicMock()
    mock_cfg.animas = {
        "sakura": AnimaModelConfig(),
        "hinata": AnimaModelConfig(supervisor="sakura"),
    }

    with (
        patch("core.config.models.load_config", return_value=mock_cfg),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
    ):
        handler = ToolHandler(
            anima_dir=sakura_dir,
            memory=memory,
            tool_registry=[],
        )
        result = handler.handle("task_tracker", {"status": "completed"})

    import json

    parsed = json.loads(result)
    assert len(parsed) >= 1
    assert any(e["subordinate_status"] == "failed" for e in parsed)


def test_task_tracker_active_excludes_failed(tmp_path: Path) -> None:
    """Test that task_tracker with status='active' excludes 'failed' tasks."""
    from unittest.mock import MagicMock

    from core.tooling.handler import ToolHandler

    animas_dir = tmp_path / "animas"
    sakura_dir = animas_dir / "sakura"
    hinata_dir = animas_dir / "hinata"
    sakura_dir.mkdir(parents=True)
    hinata_dir.mkdir(parents=True)
    (sakura_dir / "permissions.md").write_text("", encoding="utf-8")
    (sakura_dir / "state").mkdir(exist_ok=True)
    (hinata_dir / "state").mkdir(exist_ok=True)

    from core.memory.task_queue import TaskQueueManager

    sakura_tqm = TaskQueueManager(sakura_dir)
    hinata_tqm = TaskQueueManager(hinata_dir)

    hinata_task = hinata_tqm.add_task(
        source="human",
        original_instruction="subordinate task",
        assignee="hinata",
        summary="sub task",
        deadline="1h",
    )
    hinata_tqm.update_status(hinata_task.task_id, "failed")

    sakura_tqm.add_delegated_task(
        original_instruction="delegate to hinata",
        assignee="hinata",
        summary="delegated",
        deadline="1h",
        meta={"delegated_to": "hinata", "delegated_task_id": hinata_task.task_id},
    )

    memory = MagicMock()
    memory.read_permissions.return_value = ""

    from core.config.models import AnimaModelConfig

    mock_cfg = MagicMock()
    mock_cfg.animas = {
        "sakura": AnimaModelConfig(),
        "hinata": AnimaModelConfig(supervisor="sakura"),
    }

    with (
        patch("core.config.models.load_config", return_value=mock_cfg),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
    ):
        handler = ToolHandler(
            anima_dir=sakura_dir,
            memory=memory,
            tool_registry=[],
        )
        result = handler.handle("task_tracker", {"status": "active"})

    # "active" should exclude failed — so we expect no matching delegated tasks
    # (or the "no matching" message)
    import json

    try:
        parsed = json.loads(result)
        # If we get a list, it should not contain failed tasks
        if isinstance(parsed, list):
            assert not any(e["subordinate_status"] == "failed" for e in parsed)
    except json.JSONDecodeError:
        # May return i18n message like "no matching delegated tasks"
        assert "委譲" in result or "delegated" in result.lower() or "matching" in result.lower()
