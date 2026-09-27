from __future__ import annotations

import json
from pathlib import Path

from core.tasks.board.tasks import TaskStore, task_database_path
from core.tasks.queue import TaskQueueManager
from core.time_utils import now_iso


def _make_animas_dir(tmp_path: Path) -> Path:
    """Create a top-level animas directory with two animas."""
    animas_dir = tmp_path / "animas"
    for name in ("supervisor", "subordinate"):
        (animas_dir / name / "state").mkdir(parents=True)
    return animas_dir


def _add_delegated(sup_tqm: TaskQueueManager, sub_tqm: TaskQueueManager, target: str) -> tuple[str, str]:
    """Helper: create a delegated task on supervisor and a pending task on subordinate.

    Returns (supervisor_task_id, subordinate_task_id).
    """
    sub_entry = sub_tqm.add_task(
        source="anima",
        original_instruction="Do the work",
        assignee=target,
        summary="Review document",
    )
    sup_entry = sup_tqm.add_delegated_task(
        original_instruction="Do the work",
        assignee=target,
        summary="Delegated: Review document",
        meta={"delegated_to": target, "delegated_task_id": sub_entry.task_id},
    )
    return sup_entry.task_id, sub_entry.task_id


class TestFormatDelegatedForPriming:
    """Tests for TaskQueueManager.format_delegated_for_priming()."""

    def test_no_delegated_returns_empty(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        sup_tqm = TaskQueueManager(animas_dir / "supervisor")

        result = sup_tqm.format_delegated_for_priming(animas_dir)
        assert result == ""

    def test_delegated_with_pending_subordinate(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        sup_tqm = TaskQueueManager(animas_dir / "supervisor")
        sub_tqm = TaskQueueManager(animas_dir / "subordinate")

        _add_delegated(sup_tqm, sub_tqm, "subordinate")

        result = sup_tqm.format_delegated_for_priming(animas_dir)
        assert "📌" in result
        assert "subordinate" in result
        assert "⏳" in result

    def test_delegated_with_done_subordinate(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        sup_tqm = TaskQueueManager(animas_dir / "supervisor")
        sub_tqm = TaskQueueManager(animas_dir / "subordinate")

        _sup_id, sub_id = _add_delegated(sup_tqm, sub_tqm, "subordinate")
        sub_tqm.update_status(sub_id, "done")

        result = sup_tqm.format_delegated_for_priming(animas_dir)
        assert result == ""  # terminal aliases are not unfinished delegated work

    def test_delegated_with_cancelled_subordinate(self, tmp_path):
        """ "failed" was retired (A1 task-model teardown); the icon map only
        covers done/cancelled now."""
        animas_dir = _make_animas_dir(tmp_path)
        sup_tqm = TaskQueueManager(animas_dir / "supervisor")
        sub_tqm = TaskQueueManager(animas_dir / "subordinate")

        _sup_id, sub_id = _add_delegated(sup_tqm, sub_tqm, "subordinate")
        sub_tqm.update_status(sub_id, "cancelled")

        result = sup_tqm.format_delegated_for_priming(animas_dir)
        assert result == ""  # terminal aliases are not unfinished delegated work

    def test_capped_at_five(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        sup_tqm = TaskQueueManager(animas_dir / "supervisor")
        sub_tqm = TaskQueueManager(animas_dir / "subordinate")

        for _i in range(8):
            _add_delegated(sup_tqm, sub_tqm, "subordinate")

        result = sup_tqm.format_delegated_for_priming(animas_dir, budget_chars=5000)
        lines = [ln for ln in result.split("\n") if ln.startswith("- 📌")]
        assert len(lines) <= 5

    def test_budget_respected(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        sup_tqm = TaskQueueManager(animas_dir / "supervisor")
        sub_tqm = TaskQueueManager(animas_dir / "subordinate")

        for _ in range(5):
            _add_delegated(sup_tqm, sub_tqm, "subordinate")

        result = sup_tqm.format_delegated_for_priming(animas_dir, budget_chars=100)
        assert len(result) <= 200  # some tolerance for last line


def _legacy_archive_entry(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "status": "done",
        "ts": now_iso(),
        "updated_at": now_iso(),
        "source": "anima",
        "original_instruction": "historical work",
        "assignee": "subordinate",
        "summary": "done",
    }


class TestSearchArchive:
    """Tests for TaskQueueManager._search_archive()."""

    def test_finds_task_in_archive(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        target_dir = animas_dir / "subordinate"
        archive_path = target_dir / "state" / "task_queue_archive.jsonl"

        archive_data = _legacy_archive_entry("abc123")
        archive_path.write_text(json.dumps(archive_data) + "\n", encoding="utf-8")

        TaskStore(task_database_path(target_dir)).import_legacy(target_dir)
        result = TaskQueueManager._search_archive(target_dir, "abc123")
        assert result == "done"

    def test_not_in_archive_returns_none(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        target_dir = animas_dir / "subordinate"
        archive_path = target_dir / "state" / "task_queue_archive.jsonl"

        archive_data = _legacy_archive_entry("other")
        archive_path.write_text(json.dumps(archive_data) + "\n", encoding="utf-8")

        TaskStore(task_database_path(target_dir)).import_legacy(target_dir)
        result = TaskQueueManager._search_archive(target_dir, "abc123")
        assert result is None

    def test_no_archive_file_returns_none(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        result = TaskQueueManager._search_archive(animas_dir / "subordinate", "abc123")
        assert result is None

    def test_corrupted_archive_handled(self, tmp_path):
        animas_dir = _make_animas_dir(tmp_path)
        target_dir = animas_dir / "subordinate"
        archive_path = target_dir / "state" / "task_queue_archive.jsonl"

        archive_path.write_text("not json\n" + json.dumps(_legacy_archive_entry("x")) + "\n", encoding="utf-8")

        TaskStore(task_database_path(target_dir)).import_legacy(target_dir)
        result = TaskQueueManager._search_archive(target_dir, "x")
        assert result == "done"
