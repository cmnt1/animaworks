from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory.task_queue import TaskQueueManager
from core.schemas import TaskEntry


@pytest.fixture
def task_queue(tmp_path):
    """Create a TaskQueueManager with a temp anima dir."""
    anima_dir = tmp_path / "animas" / "test"
    (anima_dir / "state").mkdir(parents=True)
    return TaskQueueManager(anima_dir)


class TestAddTask:
    def test_add_task_creates_entry(self, task_queue):
        entry = task_queue.add_task(
            source="human",
            original_instruction="Issue全取得してPR作成",
            assignee="rin",
            summary="Issue取得とPR作成",
        )
        assert isinstance(entry, TaskEntry)
        assert entry.source == "human"
        assert entry.assignee == "rin"
        assert entry.status == "pending"
        assert len(entry.task_id) == 12

    def test_add_task_persists_to_jsonl(self, task_queue):
        task_queue.add_task(
            source="human",
            original_instruction="test",
            assignee="rin",
            summary="test",
        )
        assert task_queue.queue_path.exists()
        lines = task_queue.queue_path.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["source"] == "human"

    def test_add_multiple_tasks(self, task_queue):
        task_queue.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
        task_queue.add_task(source="anima", original_instruction="t2", assignee="b", summary="s2")
        tasks = task_queue.list_tasks()
        assert len(tasks) == 2

    def test_add_task_with_relay_chain(self, task_queue):
        entry = task_queue.add_task(
            source="human",
            original_instruction="test",
            assignee="rin",
            summary="test",
            relay_chain=["taka", "sakura", "rin"],
        )
        assert entry.relay_chain == ["taka", "sakura", "rin"]

    def test_add_task_with_deadline(self, task_queue):
        entry = task_queue.add_task(
            source="human",
            original_instruction="test",
            assignee="rin",
            summary="test",
            deadline="2026-03-01T00:00:00",
        )
        assert entry.deadline == "2026-03-01T00:00:00"


class TestUpdateStatus:
    def test_update_status(self, task_queue):
        entry = task_queue.add_task(
            source="human", original_instruction="t", assignee="a", summary="s",
        )
        updated = task_queue.update_status(entry.task_id, "in_progress")
        assert updated is not None
        assert updated.status == "in_progress"

    def test_update_status_persists(self, task_queue):
        entry = task_queue.add_task(
            source="human", original_instruction="t", assignee="a", summary="s",
        )
        task_queue.update_status(entry.task_id, "done")
        # Reload from file
        tasks = task_queue.list_tasks()
        done_tasks = [t for t in tasks if t.status == "done"]
        assert len(done_tasks) == 1

    def test_update_nonexistent_task(self, task_queue):
        result = task_queue.update_status("nonexistent", "done")
        assert result is None

    def test_update_invalid_status(self, task_queue):
        entry = task_queue.add_task(
            source="human", original_instruction="t", assignee="a", summary="s",
        )
        result = task_queue.update_status(entry.task_id, "invalid_status")
        assert result is None

    def test_update_summary(self, task_queue):
        entry = task_queue.add_task(
            source="human", original_instruction="t", assignee="a", summary="original",
        )
        updated = task_queue.update_status(entry.task_id, "in_progress", summary="updated")
        assert updated.summary == "updated"


class TestGetPending:
    def test_get_pending_empty(self, task_queue):
        assert task_queue.get_pending() == []

    def test_get_pending_filters_done(self, task_queue):
        e1 = task_queue.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
        e2 = task_queue.add_task(source="human", original_instruction="t2", assignee="b", summary="s2")
        task_queue.update_status(e1.task_id, "done")
        pending = task_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].task_id == e2.task_id

    def test_get_pending_includes_in_progress(self, task_queue):
        e1 = task_queue.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
        task_queue.update_status(e1.task_id, "in_progress")
        pending = task_queue.get_pending()
        assert len(pending) == 1


class TestGetHumanTasks:
    def test_get_human_tasks_filters_source(self, task_queue):
        task_queue.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
        task_queue.add_task(source="anima", original_instruction="t2", assignee="b", summary="s2")
        human = task_queue.get_human_tasks()
        assert len(human) == 1
        assert human[0].source == "human"


class TestFormatForPriming:
    def test_format_empty(self, task_queue):
        assert task_queue.format_for_priming() == ""

    def test_format_human_high_priority(self, task_queue):
        task_queue.add_task(source="human", original_instruction="t", assignee="a", summary="Important task")
        output = task_queue.format_for_priming()
        assert "🔴 HIGH" in output
        assert "Important task" in output

    def test_format_anima_normal_priority(self, task_queue):
        task_queue.add_task(source="anima", original_instruction="t", assignee="a", summary="Normal task")
        output = task_queue.format_for_priming()
        assert "⚪" in output
        assert "Normal task" in output

    def test_format_respects_budget(self, task_queue):
        # Add many tasks
        for i in range(50):
            task_queue.add_task(
                source="human", original_instruction=f"task {i}", assignee="a",
                summary=f"Very long task description number {i} with lots of detail",
            )
        output = task_queue.format_for_priming(budget_tokens=100)
        # Should be limited by budget (100 tokens * 4 chars = 400 chars)
        assert len(output) <= 500  # Some margin

    def test_format_shows_relay_chain(self, task_queue):
        task_queue.add_task(
            source="human", original_instruction="t", assignee="rin",
            summary="Delegated task", relay_chain=["taka", "sakura", "rin"],
        )
        output = task_queue.format_for_priming()
        assert "chain:" in output
        assert "taka" in output


class TestCompact:
    def test_compact_removes_done_tasks(self, task_queue):
        e1 = task_queue.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
        e2 = task_queue.add_task(source="human", original_instruction="t2", assignee="b", summary="s2")
        task_queue.update_status(e1.task_id, "done")
        removed = task_queue.compact()
        assert removed == 1
        tasks = task_queue.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].task_id == e2.task_id

    def test_compact_removes_cancelled_tasks(self, task_queue):
        e1 = task_queue.add_task(source="anima", original_instruction="t1", assignee="a", summary="s1")
        task_queue.update_status(e1.task_id, "cancelled")
        removed = task_queue.compact()
        assert removed == 1
        assert task_queue.list_tasks() == []

    def test_compact_no_terminal_tasks(self, task_queue):
        task_queue.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
        removed = task_queue.compact()
        assert removed == 0

    def test_compact_empty_queue(self, task_queue):
        removed = task_queue.compact()
        assert removed == 0


class TestSourceValidation:
    def test_invalid_source_raises(self, task_queue):
        with pytest.raises(ValueError, match="Invalid source"):
            task_queue.add_task(
                source="invalid",
                original_instruction="t",
                assignee="a",
                summary="s",
            )

    def test_valid_sources(self, task_queue):
        e1 = task_queue.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
        e2 = task_queue.add_task(source="anima", original_instruction="t2", assignee="b", summary="s2")
        assert e1.source == "human"
        assert e2.source == "anima"


class TestInstructionSizeCap:
    def test_long_instruction_truncated(self, task_queue):
        long_text = "x" * 20_000
        entry = task_queue.add_task(
            source="human",
            original_instruction=long_text,
            assignee="a",
            summary="s",
        )
        assert len(entry.original_instruction) == 10_000


class TestCorruptedFile:
    def test_corrupted_line_skipped(self, task_queue):
        task_queue.queue_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a corrupted line + valid line
        task_queue.add_task(source="human", original_instruction="valid", assignee="a", summary="valid task")
        with task_queue.queue_path.open("a") as f:
            f.write("THIS IS NOT VALID JSON\n")
        tasks = task_queue.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].summary == "valid task"
