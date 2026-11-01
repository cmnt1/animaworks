from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core.anima.inbox import _is_self_task_completion_notice
from core.messaging.messenger import Messenger
from core.schemas import Message
from core.tasks.board.tasks import process_identity
from core.tasks.pending_executor import PendingTaskExecutor
from core.tasks.queue import TaskQueueManager


def _claimed_task(tmp_path: Path, *, reply_to: str):
    anima_dir = tmp_path / "animas" / "worker"
    anima_dir.mkdir(parents=True)
    queue = TaskQueueManager(anima_dir)
    queue.submit(
        {
            "task_type": "llm",
            "task_id": "task-1",
            "title": "Task title",
            "description": "Do the work",
            "reply_to": reply_to,
        }
    )
    claim = queue.store.claim("worker", "task-1", process_identity())
    assert claim is not None
    return anima_dir, queue, claim


def _record_recipients(executor: PendingTaskExecutor, claim: dict, recipients: set[str]) -> None:
    tracker = SimpleNamespace(replied_to_for=Mock(return_value=recipients))
    executor._record_attempt_reported_to(
        {"task_id": claim["task_id"], "_attempt_token": claim["_attempt_token"]},
        SimpleNamespace(_tool_handler=tracker),
    )


def _finish_and_deliver(anima_dir: Path, queue: TaskQueueManager, claim: dict, messenger) -> None:
    assert queue.store.finish(claim["_attempt_token"], status="done", stop_kind="completed")
    executor = PendingTaskExecutor(SimpleNamespace(messenger=messenger), "worker", anima_dir, asyncio.Event())
    executor._deliver_task_wakeups(queue.store)


def _activity_entries(anima_dir: Path) -> list[dict]:
    entries = []
    for path in (anima_dir / "activity_log").glob("*.jsonl"):
        entries.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return entries


def test_report_to_reply_to_skips_completion_notification_and_acknowledges(tmp_path: Path) -> None:
    anima_dir, queue, claim = _claimed_task(tmp_path, reply_to="manager")
    messenger = SimpleNamespace(send=Mock())
    executor = PendingTaskExecutor(messenger, "worker", anima_dir, asyncio.Event())
    _record_recipients(executor, claim, {"manager"})

    _finish_and_deliver(anima_dir, queue, claim, messenger)

    messenger.send.assert_not_called()
    assert queue.store.wakeups("worker") == []
    records = _activity_entries(anima_dir)
    skipped = [record for record in records if record["type"] == "task_completion_notify_skipped"]
    assert len(skipped) == 1
    assert "報告済みのため完了通知を省略" in skipped[0]["summary"]
    assert skipped[0]["meta"]["attempt_token"] == claim["_attempt_token"]


def test_report_to_another_recipient_still_sends_completion_notification(tmp_path: Path) -> None:
    anima_dir, queue, claim = _claimed_task(tmp_path, reply_to="manager")
    messenger = SimpleNamespace(send=Mock())
    executor = PendingTaskExecutor(messenger, "worker", anima_dir, asyncio.Event())
    _record_recipients(executor, claim, {"reviewer"})

    _finish_and_deliver(anima_dir, queue, claim, messenger)

    messenger.send.assert_called_once()
    assert messenger.send.call_args.kwargs["to"] == "manager"
    assert queue.store.wakeups("worker") == []


def test_self_completion_wakeup_logs_event_without_creating_inbox_message(tmp_path: Path) -> None:
    anima_dir, queue, claim = _claimed_task(tmp_path, reply_to="worker")
    shared_dir = tmp_path / "shared"
    messenger = Messenger(shared_dir, "worker")

    _finish_and_deliver(anima_dir, queue, claim, messenger)

    assert list((shared_dir / "inbox" / "worker").glob("*.json")) == []
    assert queue.store.wakeups("worker") == []
    completed = [record for record in _activity_entries(anima_dir) if record["type"] == "task_completed"]
    assert len(completed) == 1
    assert completed[0]["meta"]["event"] == "task_completed"
    assert completed[0]["meta"]["attempt_token"] == claim["_attempt_token"]


def test_self_completion_notice_uses_event_metadata_with_english_body() -> None:
    notice = Message(
        from_person="worker",
        to_person="worker",
        content="Task task-1 has completed successfully.",
        meta={"event": "task_completed"},
    )
    attention = Message(
        from_person="worker",
        to_person="worker",
        content="タスク「legacy」(ID: task-1) が完了しました。",
        meta={"event": "task_needs_attention"},
    )

    assert _is_self_task_completion_notice(notice, "worker")
    assert not _is_self_task_completion_notice(attention, "worker")
