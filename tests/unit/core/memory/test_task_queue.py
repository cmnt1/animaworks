from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.tasks.queue — TaskQueueManager and task lifecycle."""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.tasks.board.tasks import TaskStore, task_database_path
from core.tasks.queue import (
    _ACTIVE_STATUSES,
    _TERMINAL_STATUSES,
    TaskPersistenceError,
    TaskQueueManager,
)

# ── Test 1: _append raises TaskPersistenceError on OSError ─────────────


def test_append_raises_task_persistence_error_on_oserror(tmp_path: Path) -> None:
    """Store write failures are translated to TaskPersistenceError."""
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)

    tqm = TaskQueueManager(anima_dir)

    with (
        patch.object(TaskStore, "apply", side_effect=OSError("read-only database")),
        pytest.raises(TaskPersistenceError),
    ):
        tqm.add_task(
            source="human",
            original_instruction="test task",
            assignee="anima",
            summary="test",
        )


# ── Test 2: "blocked"/"failed" statuses are retired ─────────────────────


@pytest.mark.parametrize("status", ["blocked", "failed"])
def test_update_status_retired_status_raises(tmp_path: Path, status: str) -> None:
    """update_status("blocked"/"failed") is rejected — both were retired.

    Use status='cancelled' and message the requester with the reason instead.
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
    )

    with pytest.raises(ValueError, match="retired"):
        tqm.update_status(entry.task_id, status)


def test_update_meta_is_durable_and_preserves_status(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)
    tqm = TaskQueueManager(anima_dir)
    entry = tqm.add_task(
        source="human",
        original_instruction="retry task",
        assignee="anima",
        summary="retry task",
        meta={"task_desc": {"title": "retry"}},
    )

    updated = tqm.update_meta(entry.task_id, {"retry_count": 2})

    assert updated is not None
    assert updated.status == "pending"
    assert updated.meta["task_desc"] == {"title": "retry"}
    assert updated.meta["retry_count"] == 2

    reloaded = TaskQueueManager(anima_dir).get_task_by_id(entry.task_id)
    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.meta["retry_count"] == 2


# ── Test 3: _TERMINAL_STATUSES and compact() ────────────────────────────


def test_compact_removes_terminal_statuses(tmp_path: Path) -> None:
    """Test that compact() removes "done" and "cancelled" tasks.

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
    )
    e2 = tqm.add_task(
        source="human",
        original_instruction="task 2",
        assignee="anima",
        summary="in progress",
    )
    e3 = tqm.add_task(
        source="human",
        original_instruction="task 3",
        assignee="anima",
        summary="done",
    )
    e5 = tqm.add_task(
        source="human",
        original_instruction="task 5",
        assignee="anima",
        summary="cancelled",
    )

    tqm.update_status(e3.task_id, "done")
    tqm.update_status(e5.task_id, "cancelled")

    assert "failed" not in _TERMINAL_STATUSES
    assert "blocked" not in _TERMINAL_STATUSES
    assert "done" in _TERMINAL_STATUSES
    assert "cancelled" in _TERMINAL_STATUSES

    removed = tqm.compact()

    assert removed == 2  # done, cancelled
    remaining = tqm.list_tasks()
    remaining_ids = {t.task_id for t in remaining}
    assert e1.task_id in remaining_ids
    assert e2.task_id in remaining_ids
    assert e3.task_id not in remaining_ids
    assert e5.task_id not in remaining_ids


# ── Test 4: task_tracker filters "cancelled" correctly ───────────────────


def test_task_tracker_completed_includes_cancelled(tmp_path: Path) -> None:
    """Test that task_tracker with status='completed' includes 'cancelled' tasks."""
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
    from core.tasks.queue import TaskQueueManager

    sakura_tqm = TaskQueueManager(sakura_dir)
    hinata_tqm = TaskQueueManager(hinata_dir)

    hinata_task = hinata_tqm.submit(
        {"task_id": "cancelled-child", "title": "sub task", "description": "subordinate task"}
    )
    hinata_tqm.update_status(hinata_task.task_id, "cancelled")
    sakura_tqm.store.alias("sakura", "delegated-cancelled", "hinata", hinata_task.task_id)

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
    assert any(e["subordinate_status"] == "cancelled" for e in parsed)


def test_task_tracker_active_excludes_cancelled(tmp_path: Path) -> None:
    """Test that task_tracker with status='active' excludes 'cancelled' tasks."""
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

    from core.tasks.queue import TaskQueueManager

    sakura_tqm = TaskQueueManager(sakura_dir)
    hinata_tqm = TaskQueueManager(hinata_dir)

    hinata_task = hinata_tqm.submit(
        {"task_id": "cancelled-child", "title": "sub task", "description": "subordinate task"}
    )
    hinata_tqm.update_status(hinata_task.task_id, "cancelled")
    sakura_tqm.store.alias("sakura", "delegated-cancelled", "hinata", hinata_task.task_id)

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

    # "active" should exclude cancelled — so we expect no matching delegated tasks
    # (or the "no matching" message)
    import json

    try:
        parsed = json.loads(result)
        # If we get a list, it should not contain cancelled tasks
        if isinstance(parsed, list):
            assert not any(e["subordinate_status"] == "cancelled" for e in parsed)
    except json.JSONDecodeError:
        # May return i18n message like "no matching delegated tasks"
        assert "委譲" in result or "delegated" in result.lower() or "matching" in result.lower()


# ── Test: compact() creates archive file ──────────────────────────────


def _make_tasks_with_statuses(tqm: TaskQueueManager) -> dict[str, str]:
    """Helper: create tasks and update to various statuses. Returns {task_id: status}."""
    ids: dict[str, str] = {}
    for status in ("pending", "in_progress", "done", "cancelled", "delegated"):
        e = tqm.add_task(
            source="human",
            original_instruction=f"instruction for {status} task " + "x" * 300,
            assignee="anima",
            summary=f"summary-{status}",
        )
        if status != "pending":
            tqm.update_status(e.task_id, status)
        ids[e.task_id] = status
    return ids


def test_compact_archives_records_without_second_ledger(tmp_path: Path) -> None:
    """Archive is a view of canonical records, not a second file authority."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    _make_tasks_with_statuses(tqm)
    assert not tqm.archive_path.exists()

    removed = tqm.compact()

    assert removed == 2  # done, cancelled
    assert not tqm.archive_path.exists()
    assert len(tqm._load_all(include_archived=True)) - len(tqm._load_all()) == 2


def test_compact_archive_contains_correct_tasks(tmp_path: Path) -> None:
    """Archive should contain exactly the terminal tasks with correct fields."""

    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    ids = _make_tasks_with_statuses(tqm)
    tqm.compact()

    active_ids = set(tqm._load_all())
    archived = [
        entry.model_dump() for tid, entry in tqm._load_all(include_archived=True).items() if tid not in active_ids
    ]

    archived_ids = {a["task_id"] for a in archived}
    for tid, status in ids.items():
        if status in _TERMINAL_STATUSES:
            assert tid in archived_ids, f"Terminal task {tid} ({status}) not in archive"
        else:
            assert tid not in archived_ids, f"Active task {tid} ({status}) should not be in archive"

    for a in archived:
        assert "original_instruction" in a
        assert "summary" in a
        assert a["status"] in _TERMINAL_STATUSES


def test_compact_queue_retains_only_active(tmp_path: Path) -> None:
    """After compact, queue should contain only non-terminal tasks."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    ids = _make_tasks_with_statuses(tqm)
    tqm.compact()

    all_tasks = tqm._load_all()
    for tid, entry in all_tasks.items():
        assert entry.status not in _TERMINAL_STATUSES, f"Terminal task {tid} still in queue"
    assert len(all_tasks) == sum(1 for s in ids.values() if s not in _TERMINAL_STATUSES)


def test_compact_appends_to_existing_archive(tmp_path: Path) -> None:
    """Multiple compact() calls should append to archive, not overwrite."""

    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    e1 = tqm.add_task(source="human", original_instruction="t1", assignee="a", summary="s1")
    tqm.update_status(e1.task_id, "done")
    tqm.compact()

    e2 = tqm.add_task(source="human", original_instruction="t2", assignee="a", summary="s2")
    tqm.update_status(e2.task_id, "cancelled")
    tqm.compact()

    archived_ids = set(tqm._load_all(include_archived=True))
    assert len(archived_ids) == 2
    assert e1.task_id in archived_ids
    assert e2.task_id in archived_ids


def test_compact_no_terminal_returns_zero(tmp_path: Path) -> None:
    """compact() with no terminal tasks should return 0 and not create archive."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    tqm.add_task(source="human", original_instruction="t", assignee="a", summary="s")
    assert tqm.compact() == 0
    assert not tqm.archive_path.exists()


# ── Test: list_tasks default returns only active ─────────────────────


def test_list_tasks_default_active_only(tmp_path: Path) -> None:
    """list_tasks() without filter should return only active statuses."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    ids = _make_tasks_with_statuses(tqm)
    result = tqm.list_tasks()

    result_statuses = {t.status for t in result}
    assert result_statuses <= _ACTIVE_STATUSES
    assert len(result) == sum(1 for s in ids.values() if s in _ACTIVE_STATUSES)


def test_list_tasks_status_filter_done(tmp_path: Path) -> None:
    """list_tasks(status='done') should return only done tasks."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    _make_tasks_with_statuses(tqm)
    result = tqm.list_tasks(status="done")

    assert all(t.status == "done" for t in result)
    assert len(result) == 1


def test_list_tasks_status_filter_delegated(tmp_path: Path) -> None:
    """list_tasks(status='delegated') returns delegated tasks."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    _make_tasks_with_statuses(tqm)
    result = tqm.list_tasks(status="delegated")

    assert all(t.status == "delegated" for t in result)
    assert len(result) == 1


# ── Test: _handle_list_tasks detail and truncation ───────────────────


def test_handle_list_tasks_truncates_instruction(tmp_path: Path) -> None:
    """_handle_list_tasks without detail truncates original_instruction."""
    import json as _json

    from core.tooling.handler_skills import _INSTRUCTION_TRUNCATE_LEN

    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    long_instruction = "A" * 500
    tqm.add_task(
        source="human",
        original_instruction=long_instruction,
        assignee="anima",
        summary="test",
    )

    from core.tooling.handler_skills import SkillsToolsMixin

    mixin = SkillsToolsMixin.__new__(SkillsToolsMixin)
    mixin._anima_dir = anima_dir

    result = mixin._handle_list_tasks({})
    parsed = _json.loads(result)
    assert len(parsed) == 1
    instr = parsed[0]["original_instruction"]
    assert len(instr) == _INSTRUCTION_TRUNCATE_LEN + 3  # 200 + "..."
    assert instr.endswith("...")


def test_handle_list_tasks_detail_returns_full(tmp_path: Path) -> None:
    """_handle_list_tasks with detail=true returns full original_instruction."""
    import json as _json

    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    long_instruction = "B" * 500
    tqm.add_task(
        source="human",
        original_instruction=long_instruction,
        assignee="anima",
        summary="test",
    )

    from core.tooling.handler_skills import SkillsToolsMixin

    mixin = SkillsToolsMixin.__new__(SkillsToolsMixin)
    mixin._anima_dir = anima_dir

    result = mixin._handle_list_tasks({"detail": True})
    parsed = _json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["original_instruction"] == long_instruction


def test_handle_list_tasks_no_indent(tmp_path: Path) -> None:
    """list_tasks output should not contain indentation (compact JSON)."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    tqm.add_task(
        source="human",
        original_instruction="short",
        assignee="anima",
        summary="test",
    )

    from core.tooling.handler_skills import SkillsToolsMixin

    mixin = SkillsToolsMixin.__new__(SkillsToolsMixin)
    mixin._anima_dir = anima_dir

    result = mixin._handle_list_tasks({})
    assert "\n  " not in result


# ── Test: add_task task_id, meta, status (submit_tasks support) ────────────────


def test_add_task_with_task_id_uses_provided_id(tmp_path: Path) -> None:
    """add_task with task_id uses the provided ID instead of generating one."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    entry = tqm.add_task(
        source="anima",
        original_instruction="compile",
        assignee="self",
        summary="コンパイル",
        task_id="compile123",
    )
    assert entry.task_id == "compile123"


def test_add_task_with_meta_and_status_in_progress(tmp_path: Path) -> None:
    """add_task with meta and status=in_progress for TaskExec tracking."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    entry = tqm.add_task(
        source="anima",
        original_instruction="run build",
        assignee="self",
        summary="ビルド実行",
        task_id="build001",
        meta={"executor": "taskexec"},
        status="in_progress",
    )
    assert entry.status == "in_progress"
    assert entry.meta.get("executor") == "taskexec"


# ── Test: format_for_priming auto-taskexec marker ────────────────────────
# (get_failed_taskexec and the format_for_priming "failed" section were
# removed along with the "failed" status — see A1 task-model teardown plan.)


def test_format_for_priming_shows_auto_taskexec_for_in_progress(tmp_path: Path) -> None:
    """format_for_priming shows (auto: TaskExec) for in_progress tasks with meta.executor."""
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    tqm.add_task(
        source="anima",
        original_instruction="compile",
        assignee="self",
        summary="コンパイル",
        task_id="abc12345",
        meta={"executor": "taskexec"},
        status="in_progress",
    )

    result = tqm.format_for_priming(budget_tokens=500)
    assert "(auto: TaskExec)" in result
    assert "abc12345" in result or "abc1234" in result


# ── Terminal status updates ─────────────────────────


def _tqm_with_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str = "sakura"):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))
    anima_dir = data_dir / "animas" / name
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)
    return TaskQueueManager(anima_dir), data_dir


def test_update_status_terminal_marks_task_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Terminal status simply marks the canonical task terminal (no metadata)."""
    tqm, _data_dir = _tqm_with_data_dir(tmp_path, monkeypatch)
    entry = tqm.add_task(
        source="human",
        original_instruction="delegate work",
        assignee="sakura",
        summary="delegate work",
        task_id="task-term-1",
    )

    result = tqm.update_status(entry.task_id, "done")

    assert result is not None
    assert result.status == "done"


def test_update_status_terminal_then_pending_reactivates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A terminal task can be re-queued to pending."""
    tqm, _data_dir = _tqm_with_data_dir(tmp_path, monkeypatch)
    entry = tqm.add_task(
        source="human",
        original_instruction="revivable work",
        assignee="sakura",
        summary="revivable work",
        task_id="task-revive-1",
    )

    result = tqm.update_status(entry.task_id, "done")
    assert result is not None and result.status == "done"

    result = tqm.update_status(entry.task_id, "pending")
    assert result is not None and result.status == "pending"


def test_update_status_terminal_succeeds_without_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Terminal status never touches a TaskBoard metadata row (none exists anymore)."""
    tqm, _data_dir = _tqm_with_data_dir(tmp_path, monkeypatch)
    entry = tqm.add_task(
        source="human",
        original_instruction="plain task",
        assignee="sakura",
        summary="plain task",
        task_id="task-no-meta",
    )

    result = tqm.update_status(entry.task_id, "done")

    assert result is not None
    assert result.status == "done"


def test_update_status_non_terminal_changes_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-terminal transitions just change the canonical status."""
    tqm, _data_dir = _tqm_with_data_dir(tmp_path, monkeypatch)
    entry = tqm.add_task(
        source="human",
        original_instruction="active task",
        assignee="sakura",
        summary="active task",
        task_id="task-active",
    )

    result = tqm.update_status(entry.task_id, "in_progress")

    assert result is not None
    assert result.status == "in_progress"


# ── Legacy jsonl compat: blocked/failed/deadline rows read as pending ──────


def test_load_all_remaps_legacy_blocked_creation_row_to_pending(tmp_path: Path) -> None:
    """A pre-teardown jsonl row created with status='blocked' plus deadline/
    unblock_check fields must load as 'pending' with no exception, and the
    retired fields must not leak into the reconstructed TaskEntry."""
    import json

    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    queue_path = anima_dir / "state" / "task_queue.jsonl"
    legacy_row = {
        "task_id": "legacy-blocked-1",
        "ts": "2026-08-01T00:00:00+09:00",
        "source": "human",
        "original_instruction": "legacy work",
        "assignee": "anima",
        "status": "blocked",
        "summary": "legacy blocked task",
        "deadline": "2026-08-01T01:00:00+09:00",
        "relay_chain": [],
        "updated_at": "2026-08-01T00:30:00+09:00",
        "meta": {
            "unblock_check": "test -w .",
            "blocked_at": "2026-08-01T00:30:00+09:00",
            "unblock_check_failures": 2,
        },
    }
    queue_path.write_text(json.dumps(legacy_row, ensure_ascii=False) + "\n", encoding="utf-8")

    TaskStore(task_database_path(anima_dir)).import_legacy(anima_dir)
    tqm = TaskQueueManager(anima_dir)
    entry = tqm.get_task_by_id("legacy-blocked-1")

    assert entry is not None
    assert entry.status == "pending"
    assert not hasattr(entry, "deadline")
    # legacy meta keys are preserved verbatim (they are just data now)
    assert entry.meta.get("unblock_check") == "test -w ."


def test_post_migration_jsonl_writes_cannot_change_canonical_state(tmp_path: Path) -> None:
    """Old writers cannot compete with the canonical task authority."""
    import json

    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    tqm = TaskQueueManager(anima_dir)

    entry = tqm.add_task(
        source="anima",
        original_instruction="do a thing",
        assignee="anima",
        summary="do a thing",
        task_id="legacy-failed-1",
    )

    # Hand-append a legacy "failed" update event (as an old TaskExec runner would have).
    legacy_update = {
        "task_id": entry.task_id,
        "status": "failed",
        "updated_at": "2026-08-01T02:00:00+09:00",
        "summary": "crashed: OOM",
        "_event": "update",
    }
    with tqm.queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(legacy_update, ensure_ascii=False) + "\n")

    reloaded = tqm.get_task_by_id(entry.task_id)
    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.summary == "do a thing"

    # The queue must remain usable — no exception building the priming view either.
    assert isinstance(tqm.format_for_priming(), str)


def test_update_status_pending_on_legacy_blocked_task_succeeds(tmp_path: Path) -> None:
    """Even without touching the file directly, a legacy blocked row must not
    block a subsequent update_status() call to a valid status."""
    import json

    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True)
    queue_path = anima_dir / "state" / "task_queue.jsonl"
    legacy_row = {
        "task_id": "legacy-blocked-2",
        "ts": "2026-08-01T00:00:00+09:00",
        "source": "human",
        "original_instruction": "legacy work 2",
        "assignee": "anima",
        "status": "blocked",
        "summary": "legacy blocked task 2",
        "relay_chain": [],
        "updated_at": "2026-08-01T00:30:00+09:00",
        "meta": {},
    }
    queue_path.write_text(json.dumps(legacy_row, ensure_ascii=False) + "\n", encoding="utf-8")

    TaskStore(task_database_path(anima_dir)).import_legacy(anima_dir)
    tqm = TaskQueueManager(anima_dir)
    result = tqm.update_status("legacy-blocked-2", "cancelled", summary="won't proceed")
    assert result is not None
    assert result.status == "cancelled"
