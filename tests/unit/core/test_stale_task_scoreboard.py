from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core._anima_heartbeat import HeartbeatMixin, _build_stale_task_scoreboard
from core.memory.task_queue import TaskQueueManager
from core.time_utils import now_local


def _heartbeat(anima_dir: Path) -> HeartbeatMixin:
    heartbeat = HeartbeatMixin()
    heartbeat.anima_dir = anima_dir
    heartbeat.name = anima_dir.name
    heartbeat.memory = SimpleNamespace(read_heartbeat_config=lambda: "checklist")
    heartbeat._build_state_cleanup_instruction = lambda: None
    heartbeat._build_background_context_parts = lambda: []
    return heartbeat


def _prompt(name: str, **kwargs: object) -> str:
    if name == "fragments/stale_task_scoreboard":
        return f"scoreboard\n{kwargs['tasks']}{kwargs['overflow']}"
    return name


async def test_heartbeat_injects_stale_task_scoreboard(tmp_path: Path) -> None:
    anima_dir = tmp_path / "worker"
    manager = TaskQueueManager(anima_dir)
    current = now_local()
    with patch("core.memory.task_queue.now_iso", return_value=(current - timedelta(hours=25)).isoformat()):
        manager.add_task(
            source="human",
            original_instruction="finish",
            assignee="worker",
            summary="stale task\ncontinued",
            task_id="1234567890123456",
        )

    with (
        patch("core._anima_heartbeat.now_local", return_value=current),
        patch("core._anima_heartbeat.load_prompt", side_effect=_prompt),
        patch("core._anima_heartbeat._build_curator_review_part", return_value=None),
    ):
        parts = await _heartbeat(anima_dir)._build_heartbeat_prompt()

    scoreboard = next(part for part in parts if part.startswith("scoreboard"))
    assert "⚠️ 123456789012 | pending | 25h | stale task continued" in scoreboard


async def test_heartbeat_omits_scoreboard_without_active_tasks(tmp_path: Path) -> None:
    anima_dir = tmp_path / "worker"
    anima_dir.mkdir()

    with (
        patch("core._anima_heartbeat.load_prompt", side_effect=_prompt),
        patch("core._anima_heartbeat._build_curator_review_part", return_value=None),
    ):
        parts = await _heartbeat(anima_dir)._build_heartbeat_prompt()

    assert all(not part.startswith("scoreboard") for part in parts)


def test_scoreboard_limits_to_twenty_oldest_tasks(tmp_path: Path) -> None:
    anima_dir = tmp_path / "worker"
    manager = TaskQueueManager(anima_dir)
    current = now_local()
    for index in range(22):
        created = current - timedelta(hours=22 - index)
        with patch("core.memory.task_queue.now_iso", return_value=created.isoformat()):
            manager.add_task(
                source="human",
                original_instruction="finish",
                assignee="worker",
                summary=f"task {index}",
                task_id=f"task-{index:02d}",
            )

    with (
        patch("core._anima_heartbeat.now_local", return_value=current),
        patch("core._anima_heartbeat.load_prompt", side_effect=_prompt),
        patch("core._anima_heartbeat.t", return_value="他2件"),
    ):
        scoreboard = _build_stale_task_scoreboard(anima_dir, "worker")

    assert scoreboard is not None
    assert "task-00" in scoreboard and "task-19" in scoreboard
    assert "task-20" not in scoreboard and "task-21" not in scoreboard
    assert scoreboard.count(" | pending | ") == 20
    assert "他2件" in scoreboard


def test_scoreboard_below_limit_has_no_overflow_line(tmp_path: Path) -> None:
    anima_dir = tmp_path / "worker"
    manager = TaskQueueManager(anima_dir)
    manager.add_task(
        source="human",
        original_instruction="finish",
        assignee="worker",
        summary="only task",
        task_id="task-00",
    )

    with (
        patch("core._anima_heartbeat.load_prompt", side_effect=_prompt),
        patch("core._anima_heartbeat.t", return_value="SHOULD_NOT_APPEAR"),
    ):
        scoreboard = _build_stale_task_scoreboard(anima_dir, "worker")

    assert scoreboard is not None
    assert "SHOULD_NOT_APPEAR" not in scoreboard
