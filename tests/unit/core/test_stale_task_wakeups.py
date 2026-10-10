import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.tasks.pending_executor import PendingTaskExecutor
from core.tasks.queue import TaskQueueManager
from core.time_utils import now_local


def test_idle_work_gets_daily_reminders_without_replaying_attempts(tmp_path):
    queue = TaskQueueManager(tmp_path / "animas" / "worker")
    start = now_local()
    with patch("core.tasks.queue.now_iso", return_value=start.isoformat()):
        queue.add_task(
            source="anima",
            original_instruction="review",
            assignee="worker",
            summary="Review",
            task_id="backlog",
            relay_chain=["manager"],
        )
    for task_id in ["stopped", "queued", "running", "cancelled", "delegated"]:
        queue.submit({"task_id": task_id, "title": task_id, "description": "work", "reply_to": "manager"})
    with patch("core.tasks.board.tasks.now_iso", return_value=start.isoformat()):
        claim = queue.store.claim("worker", "stopped", {"pid": 1})
        queue.store.finish(claim["_attempt_token"], status="pending", stop_kind="crash")
        queue.store.acknowledge_wakeup("worker", claim["_attempt_token"])
        queue.store.claim("worker", "running", {"pid": 1}, max_active=2)
    queue.update_status("cancelled", "cancelled")
    queue.update_status("delegated", "delegated")

    with patch("core.tasks.board.tasks.now_iso", return_value=(start + timedelta(hours=23)).isoformat()):
        queue.store.enqueue_stale_wakeups("worker")
    assert queue.store.wakeups("worker") == []
    with patch("core.tasks.board.tasks.now_iso", return_value=(start + timedelta(hours=25)).isoformat()):
        queue.store.enqueue_stale_wakeups("worker")
        events = queue.store.wakeups("worker")
        assert {e["task_id"]: e["reason"] for e in events} == {
            "backlog": "stale_backlog",
            "stopped": "stale_incomplete",
        }
        for event in events:
            queue.store.acknowledge_wakeup("worker", event["attempt_token"])
        queue.store.enqueue_stale_wakeups("worker")
        assert queue.store.wakeups("worker") == []
    with patch("core.tasks.board.tasks.now_iso", return_value=(start + timedelta(hours=49)).isoformat()):
        queue.store.enqueue_stale_wakeups("worker")
    assert len(queue.store.wakeups("worker")) == 2
    with patch("core.tasks.board.tasks.now_iso", return_value=(start + timedelta(hours=73)).isoformat()):
        queue.store.enqueue_stale_wakeups("worker")
    assert len(queue.store.wakeups("worker")) == 2  # Offline reminders do not accumulate.
    assert "stopped" not in {p["task_id"] for p in queue.store.pending("worker")}
    assert queue.get_task_by_id("backlog").updated_at == start.isoformat()


def test_stale_notice_reaches_requester_and_cancellation_suppresses_it(tmp_path):
    queue = TaskQueueManager(tmp_path / "animas" / "worker")
    old = (now_local() - timedelta(days=2)).isoformat()
    with patch("core.tasks.queue.now_iso", return_value=old):
        for task_id in ["backlog", "cancelled"]:
            queue.add_task(
                source="anima",
                original_instruction="review",
                assignee="worker",
                summary="Review",
                task_id=task_id,
                relay_chain=["manager"],
            )
    queue.store.enqueue_stale_wakeups("worker")
    queue.update_status("cancelled", "cancelled")
    anima = SimpleNamespace(messenger=SimpleNamespace(send=Mock(side_effect=OSError("offline"))))
    executor = PendingTaskExecutor(anima, "worker", queue.anima_dir, asyncio.Event())
    executor._deliver_task_wakeups(queue.store)
    assert [event["task_id"] for event in queue.store.wakeups("worker")] == ["backlog"]
    anima.messenger.send.side_effect = None
    anima.messenger.send.reset_mock()
    executor._deliver_task_wakeups(queue.store)
    assert {call.kwargs["to"] for call in anima.messenger.send.call_args_list} == {"manager", "worker"}
    assert all("submit_tasks" in call.kwargs["content"] for call in anima.messenger.send.call_args_list)
    assert queue.store.wakeups("worker") == []


def test_watcher_checks_stale_work_independently_of_heartbeat(tmp_path):
    queue = TaskQueueManager(tmp_path / "animas" / "worker")
    with patch("core.tasks.queue.now_iso", return_value=(now_local() - timedelta(days=2)).isoformat()):
        queue.add_task(source="human", original_instruction="review", assignee="worker", summary="Review")
    anima = SimpleNamespace(messenger=SimpleNamespace(send=Mock()), heartbeat_enabled=False)
    executor = PendingTaskExecutor(anima, "worker", queue.anima_dir, asyncio.Event())
    assert executor._claim_canonical_pending_tasks() == []
    assert anima.messenger.send.called
