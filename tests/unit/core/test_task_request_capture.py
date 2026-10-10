from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.task_request_capture import capture_task_request_from_message
from core.tasks.queue import TaskQueueManager


def _capture(root: Path, message_id: str = "message-one") -> str | None:
    return capture_task_request_from_message(
        animas_dir=root,
        from_person="manager",
        to_person="worker",
        content="正式証跡を確認してください。",
        message_id=message_id,
        thread_id="thread-one",
        intent="question",
    )


def test_capture_publishes_executable_input_atomically(tmp_path):
    root = tmp_path / "animas"
    (root / "manager").mkdir(parents=True)
    (root / "worker").mkdir()
    task_id = _capture(root)
    queue = TaskQueueManager(root / "worker")
    payloads = queue.store.pending("worker")
    assert len(payloads) == 1
    assert payloads[0]["task_id"] == task_id
    assert payloads[0]["description"] == "正式証跡を確認してください。"
    assert payloads[0]["reply_to"] == "manager"
    assert queue.get_task_by_id(task_id).relay_chain == ["manager"]
    assert not (root / "worker" / "state" / "pending").exists()


def test_concurrent_capture_and_redelivery_after_cancel_do_not_duplicate(tmp_path):
    root = tmp_path / "animas"
    (root / "manager").mkdir(parents=True)
    (root / "worker").mkdir()
    queue = TaskQueueManager(root / "worker")
    assert queue.store.read("worker") == {}  # Initialize schema before concurrent deliveries.
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(_capture, [root] * 8))
    assert None not in ids and len(set(ids)) == 1
    assert len(queue.store.read("worker")) == 1
    queue.update_status(ids[0], "cancelled")
    assert _capture(root) == ids[0]
    assert queue.get_task_by_id(ids[0]).status == "cancelled"
    assert queue.store.pending("worker") == []


def test_failed_capture_leaves_no_nonexecutable_backlog(tmp_path):
    root = tmp_path / "animas"
    (root / "manager").mkdir(parents=True)
    (root / "worker").mkdir()
    with patch("core.tasks.board.tasks.TaskStore.submit", side_effect=OSError("disk full")):
        assert _capture(root) is None
    assert TaskQueueManager(root / "worker").store.read("worker") == {}
