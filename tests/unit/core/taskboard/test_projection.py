from __future__ import annotations

from pathlib import Path

from core.memory.task_queue import TaskQueueManager
from core.taskboard.models import AttentionVisibility, BoardColumn
from core.taskboard.projector import QUEUE_STATUS_TO_COLUMN, compute_needs_human, project_all, project_anima
from core.taskboard.store import TaskBoardStore


def _queue(tmp_path: Path, anima_name: str) -> TaskQueueManager:
    anima_dir = tmp_path / "animas" / anima_name
    (anima_dir / "state").mkdir(parents=True)
    return TaskQueueManager(anima_dir)


def test_projection_replays_latest_status_and_skips_corrupt_lines(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    task = manager.add_task(
        source="human",
        original_instruction="implement projection",
        assignee="sakura",
        summary="projection",
        task_id="task-1",
    )
    manager.update_status(task.task_id, "in_progress", summary="projection running")
    manager.queue_path.write_text(manager.queue_path.read_text(encoding="utf-8") + "{corrupt-json\n", encoding="utf-8")

    projected = project_anima(manager.anima_dir, TaskBoardStore(tmp_path / "taskboard.sqlite3"))

    assert len(projected) == 1
    assert projected[0].task_id == "task-1"
    assert projected[0].queue_status == "in_progress"
    assert projected[0].summary == "projection running"
    assert projected[0].column == BoardColumn.RUNNING


def test_projection_splits_human_source_by_instruction_origin(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "kanna")
    direct = manager.add_task(
        source="human",
        original_instruction="direct owner request",
        assignee="kanna",
        summary="direct owner request",
        task_id="human-direct",
        meta={"instruction_origin": "human"},
    )
    dashboard = manager.add_task(
        source="human",
        original_instruction="dashboard managed request",
        assignee="kanna",
        summary="dashboard managed request",
        task_id="machine-dashboard",
        meta={"origin": "daily-ops-dashboard"},
    )

    projected = project_anima(manager.anima_dir, TaskBoardStore(tmp_path / "taskboard.sqlite3"))
    by_id = {task.task_id: task for task in projected}

    assert by_id[direct.task_id].instruction_origin == "human"
    assert by_id[dashboard.task_id].instruction_origin == "machine"


def test_projection_status_to_column_mapping(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    statuses = ["pending", "in_progress", "blocked", "delegated", "failed", "done", "cancelled"]

    for status in statuses:
        task = manager.add_task(
            source="human",
            original_instruction=status,
            assignee="sakura",
            summary=status,
            task_id=f"task-{status}",
            status="in_progress" if status == "in_progress" else "pending",
        )
        if status not in {"pending", "in_progress"}:
            manager.update_status(task.task_id, status)

    projected = project_anima(
        manager.anima_dir,
        TaskBoardStore(tmp_path / "taskboard.sqlite3"),
        include_archived=True,
    )
    by_status = {task.queue_status: task for task in projected}

    assert {status: by_status[status].column for status in statuses} == QUEUE_STATUS_TO_COLUMN
    for terminal_status in {"done", "cancelled"}:
        assert by_status[terminal_status].visibility == AttentionVisibility.ARCHIVED
    assert by_status["failed"].visibility == AttentionVisibility.ACTIVE


def test_stale_active_tasks_go_to_review_without_mutating_queue_status(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    task = manager.add_task(
        source="human",
        original_instruction="keep queue status",
        assignee="sakura",
        summary="keep queue status",
        task_id="task-1",
    )
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    projected = project_anima(manager.anima_dir, store)

    assert projected[0].queue_status == "pending"
    assert projected[0].column == BoardColumn.TODO

    manager.update_status(task.task_id, "pending")
    # Force the task past the TaskBoard stale threshold without changing its
    # durable queue status.
    manager.queue_path.write_text(
        manager.queue_path.read_text(encoding="utf-8").replace(
            '"updated_at": "' + manager.get_task_by_id(task.task_id).updated_at + '"',
            '"updated_at": "2000-01-01T00:00:00+09:00"',
        ),
        encoding="utf-8",
    )

    projected = project_anima(manager.anima_dir, store)

    assert projected[0].queue_status == "pending"
    assert projected[0].column == BoardColumn.REVIEW
    assert manager.get_task_by_id(task.task_id).status == "pending"


def test_stale_pending_task_waits_when_same_anima_has_running_task(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "kanna")
    running = manager.add_task(
        source="human",
        original_instruction="active repair",
        assignee="kanna",
        summary="active repair",
        task_id="running-task",
        status="in_progress",
    )
    pending = manager.add_task(
        source="human",
        original_instruction="queued final evidence",
        assignee="kanna",
        summary="queued final evidence",
        task_id="queued-task",
    )
    manager.update_status(pending.task_id, "pending")
    manager.queue_path.write_text(
        manager.queue_path.read_text(encoding="utf-8").replace(
            '"updated_at": "' + manager.get_task_by_id(pending.task_id).updated_at + '"',
            '"updated_at": "2000-01-01T00:00:00+09:00"',
        ),
        encoding="utf-8",
    )

    projected = project_anima(manager.anima_dir, TaskBoardStore(tmp_path / "taskboard.sqlite3"))
    by_id = {task.task_id: task for task in projected}

    assert by_id[running.task_id].column == BoardColumn.RUNNING
    assert by_id[pending.task_id].queue_status == "pending"
    assert by_id[pending.task_id].column == BoardColumn.WAITING
    assert manager.get_task_by_id(pending.task_id).status == "pending"


def test_metadata_column_overrides_board_only_without_mutating_queue_status(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    task = manager.add_task(
        source="human",
        original_instruction="keep queue status",
        assignee="sakura",
        summary="keep queue status",
        task_id="task-1",
    )
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="sakura",
        task_id=task.task_id,
        column="blocked",
        position=5.0,
    )

    projected = project_anima(manager.anima_dir, store)

    assert projected[0].queue_status == "pending"
    assert projected[0].column == BoardColumn.BLOCKED
    assert projected[0].source_ref == "task_queue:sakura:task-1"
    assert manager.get_task_by_id(task.task_id).status == "pending"


def test_terminal_tasks_are_archived_by_default_view(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    task = manager.add_task(
        source="human",
        original_instruction="finish",
        assignee="sakura",
        summary="finish",
        task_id="task-1",
    )
    manager.update_status(task.task_id, "done")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    assert project_anima(manager.anima_dir, store) == []

    projected = project_anima(manager.anima_dir, store, include_archived=True)
    assert projected[0].visibility == AttentionVisibility.ARCHIVED
    assert projected[0].column == BoardColumn.DONE


def test_failed_tasks_stay_visible_as_blocked_by_default(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    task = manager.add_task(
        source="anima",
        original_instruction="review failure",
        assignee="sakura",
        summary="review failure",
        task_id="task-1",
        status="in_progress",
    )
    manager.update_status(task.task_id, "failed")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    projected = project_anima(manager.anima_dir, store)

    assert len(projected) == 1
    assert projected[0].visibility == AttentionVisibility.ACTIVE
    assert projected[0].column == BoardColumn.BLOCKED


def test_duplicate_failed_crons_keep_latest_only(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    meta = {"from_cron": True, "cron_task_name": "daily review", "cron_type": "command"}

    first = manager.add_task(
        source="anima",
        original_instruction="run daily review",
        assignee="sakura",
        summary="cron running",
        task_id="cron-failed-1",
        meta=meta,
    )
    manager.update_status(first.task_id, "failed", summary="cron failed")
    second = manager.add_task(
        source="anima",
        original_instruction="run daily review",
        assignee="sakura",
        summary="cron running",
        task_id="cron-failed-2",
        meta=meta,
    )
    manager.update_status(second.task_id, "failed", summary="cron failed again")

    projected = project_anima(manager.anima_dir, store)
    by_id = {task.task_id: task for task in projected}

    assert list(by_id) == [second.task_id]
    assert by_id[second.task_id].column == BoardColumn.BLOCKED

    archived = project_anima(manager.anima_dir, store, include_archived=True)
    archived_by_id = {task.task_id: task for task in archived}

    assert archived_by_id[first.task_id].visibility == AttentionVisibility.ARCHIVED
    assert archived_by_id[first.task_id].column == BoardColumn.SUPPRESSED
    assert archived_by_id[first.task_id].replaced_by == f"sakura:{second.task_id}"
    assert archived_by_id[first.task_id].tombstone_reason == "duplicate_failed_cron"


def test_failed_delegated_child_is_hidden_when_parent_was_cancelled(tmp_path: Path) -> None:
    ayane = _queue(tmp_path, "ayane")
    momoka = _queue(tmp_path, "momoka")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = momoka.add_task(
        source="anima",
        original_instruction="verify upstream note",
        assignee="momoka",
        summary="verify upstream note",
        task_id="child-failed",
    )
    momoka.update_status(child.task_id, "failed", summary="FAILED: stream disconnected")
    parent = ayane.add_delegated_task(
        original_instruction="delegate note verification",
        assignee="momoka",
        summary="delegate note verification",
        deadline="1h",
        meta={"delegated_to": "momoka", "delegated_task_id": child.task_id},
    )
    ayane.update_status(parent.task_id, "cancelled", summary="tombstoned by TaskBoard")

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert ("momoka", child.task_id) not in by_key

    archived = project_all(tmp_path / "animas", store, include_archived=True)
    archived_by_key = {(task.anima_name, task.task_id): task for task in archived}
    archived_child = archived_by_key[("momoka", child.task_id)]
    assert archived_child.visibility == AttentionVisibility.ARCHIVED
    assert archived_child.column == BoardColumn.SUPPRESSED
    assert archived_child.replaced_by == f"ayane:{parent.task_id}"


def test_missing_queue_metadata_is_hidden_unless_requested(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="sakura",
        task_id="missing",
        visibility="active",
        column="review",
        source_ref="task_queue:sakura:missing",
    )
    anima_dir = tmp_path / "animas" / "sakura"
    (anima_dir / "state").mkdir(parents=True)

    assert project_anima(anima_dir, store) == []

    projected = project_anima(anima_dir, store, include_missing=True)
    assert len(projected) == 1
    assert projected[0].queue_missing is True
    assert projected[0].column == BoardColumn.REVIEW


def test_compute_needs_human_detects_known_signals() -> None:
    # C: assignee == human
    assert compute_needs_human(assignee="Human", queue_status="pending", meta=None, notification_key=None) == (
        True,
        "assignee_human",
    )

    # B: call_human pending, queue not terminal
    assert compute_needs_human(assignee="sakura", queue_status="pending", meta=None, notification_key="nk-1") == (
        True,
        "call_human_pending",
    )

    # B suppressed when terminal
    assert compute_needs_human(assignee="sakura", queue_status="done", meta=None, notification_key="nk-1") == (
        False,
        None,
    )

    # D: explicit flag
    assert compute_needs_human(
        assignee="sakura", queue_status="blocked", meta={"needs_human": True}, notification_key=None
    ) == (True, "meta_flag")

    # D: meta blocker on blocked task
    assert compute_needs_human(
        assignee="sakura", queue_status="blocked", meta={"blocker": "human"}, notification_key=None
    ) == (True, "meta_blocker")

    # D: meta blocker ignored when not blocked
    assert compute_needs_human(
        assignee="sakura", queue_status="pending", meta={"blocker": "human"}, notification_key=None
    ) == (False, None)

    # Negative baseline
    assert compute_needs_human(
        assignee="sakura", queue_status="pending", meta={"blocker": "kanna"}, notification_key=None
    ) == (False, None)


def test_projected_task_carries_needs_human_field(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    manager.add_task(
        source="human",
        original_instruction="escalate",
        assignee="human",
        summary="escalate to human",
        task_id="task-1",
    )
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    projected = project_anima(manager.anima_dir, store)

    assert len(projected) == 1
    assert projected[0].needs_human is True
    assert projected[0].needs_human_reason == "assignee_human"


def test_projected_task_surfaces_cron_metadata(tmp_path: Path) -> None:
    manager = _queue(tmp_path, "sakura")
    manager.add_task(
        source="anima",
        original_instruction="毎朝の業務計画",
        assignee="sakura",
        summary="⏰ cron 実行中: 毎朝の業務計画",
        task_id="cron-task-1",
        status="in_progress",
        meta={"from_cron": True, "cron_task_name": "毎朝の業務計画", "cron_type": "llm"},
    )
    # Non-cron task should not get the flag
    manager.add_task(
        source="anima",
        original_instruction="regular work",
        assignee="sakura",
        summary="regular work",
        task_id="task-2",
    )
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    projected = {task.task_id: task for task in project_anima(manager.anima_dir, store)}

    cron_task = projected["cron-task-1"]
    assert cron_task.is_from_cron is True
    assert cron_task.cron_task_name == "毎朝の業務計画"

    regular = projected["task-2"]
    assert regular.is_from_cron is False
    assert regular.cron_task_name is None


def test_projected_task_surfaces_delegation_and_response_links(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    mira = _queue(tmp_path, "mira")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    mira.add_task(
        source="anima",
        original_instruction="verify public evidence",
        assignee="mira",
        summary="verify evidence",
        task_id="b1a58e0e84ae",
    )
    parent = sakura.add_delegated_task(
        original_instruction="delegate verification",
        assignee="mira",
        summary="[委譲] verify evidence",
        deadline="1h",
        meta={"delegated_to": "mira", "delegated_task_id": "b1a58e0e84ae"},
    )
    original = kanna.add_task(
        source="anima",
        original_instruction="repair article",
        assignee="kanna",
        summary="AFF-003 repair",
        task_id="051f9900fce4",
    )
    kanna.update_status(original.task_id, "done")
    kanna.compact()
    response = kanna.add_task(
        source="anima",
        original_instruction="【確認結果】051f9900fce4 は承認できません",
        assignee="kanna",
        summary="【確認結果】051f9900fce4 は承認できません",
        task_id="a3d97372f90f",
        meta={"source_from": "sakura", "source_intent": "report"},
    )

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    child_links = by_key[("mira", "b1a58e0e84ae")].related_tasks
    assert child_links[0].kind == "delegated_from"
    assert child_links[0].anima_name == "sakura"
    assert child_links[0].task_id == parent.task_id
    assert child_links[0].title == "[委譲] verify evidence"

    parent_links = by_key[("sakura", parent.task_id)].related_tasks
    assert parent_links[0].kind == "delegates_to"
    assert parent_links[0].anima_name == "mira"
    assert parent_links[0].task_id == "b1a58e0e84ae"
    assert parent_links[0].title == "verify evidence"

    response_links = by_key[("kanna", response.task_id)].related_tasks
    assert response_links[0].kind == "responds_to"
    assert response_links[0].anima_name == "kanna"
    assert response_links[0].task_id == original.task_id
    assert response_links[0].peer_name == "sakura"
    assert response_links[0].title == "AFF-003 repair"


def test_blocked_delegated_parent_waits_when_child_is_active(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    sora = _queue(tmp_path, "sora")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = sora.add_task(
        source="anima",
        original_instruction="finish verifier",
        assignee="sora",
        summary="finish verifier",
        task_id="child-blocked",
    )
    sora.update_status(child.task_id, "blocked", summary="missing evidence")
    parent = sakura.add_delegated_task(
        original_instruction="track verifier",
        assignee="sora",
        summary="track verifier",
        deadline="1h",
        meta={"delegated_to": "sora", "delegated_task_id": child.task_id},
    )
    sakura.update_status(parent.task_id, "blocked", summary="waiting for child evidence")

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert by_key[("sakura", parent.task_id)].queue_status == "blocked"
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.WAITING
    assert by_key[("sora", child.task_id)].queue_status == "blocked"
    assert by_key[("sora", child.task_id)].column == BoardColumn.BLOCKED


def test_blocked_task_waits_when_summary_references_active_tracking_task(tmp_path: Path) -> None:
    kanna = _queue(tmp_path, "kanna")
    miyu = _queue(tmp_path, "miyu")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    tracking = kanna.add_delegated_task(
        original_instruction="delegate image repair",
        assignee="miyu",
        summary="[delegate] image repair",
        deadline="1h",
        meta={"delegated_to": "miyu", "delegated_task_id": "9e221d6614c2"},
    )
    child = miyu.add_task(
        source="anima",
        original_instruction="repair image evidence",
        assignee="miyu",
        summary="repair image evidence",
        task_id="9e221d6614c2",
    )
    miyu.update_status(child.task_id, "in_progress", summary="repair running")
    parent = kanna.add_task(
        source="anima",
        original_instruction="finish evidence",
        assignee="kanna",
        summary=f"delegated to miyu ({child.task_id} / tracking: {tracking.task_id})",
        task_id="a79908bd4619",
    )
    kanna.update_status(parent.task_id, "blocked", summary=parent.summary)

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert by_key[("kanna", parent.task_id)].queue_status == "blocked"
    assert by_key[("kanna", parent.task_id)].column == BoardColumn.WAITING
    links = by_key[("kanna", parent.task_id)].related_tasks
    assert {link.task_id for link in links} == {tracking.task_id, child.task_id}


def test_blocked_task_does_not_wait_on_historical_reference_in_original_instruction(tmp_path: Path) -> None:
    kanna = _queue(tmp_path, "kanna")
    sakura = _queue(tmp_path, "sakura")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    parent = sakura.add_delegated_task(
        original_instruction="track final evidence",
        assignee="kanna",
        summary="waiting for retry",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": "de432f83bbc1"},
    )
    child = kanna.add_task(
        source="anima",
        original_instruction=f"Retry old completion notice from {parent.task_id}; produce final evidence.",
        assignee="kanna",
        summary="retry evidence",
        task_id="de432f83bbc1",
    )
    kanna.update_status(child.task_id, "blocked", summary="BLOCKED: not final evidence")

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert by_key[("kanna", child.task_id)].queue_status == "blocked"
    assert by_key[("kanna", child.task_id)].column == BoardColumn.BLOCKED
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.WAITING


def test_delegated_parent_moves_to_review_when_child_is_terminal(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = kanna.add_task(
        source="anima",
        original_instruction="fix ad evidence",
        assignee="kanna",
        summary="fix ad evidence",
        task_id="child-done",
    )
    kanna.update_status(child.task_id, "done", summary="submitted evidence")
    parent = sakura.add_delegated_task(
        original_instruction="track ad evidence",
        assignee="kanna",
        summary="[委譲] track ad evidence",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert ("kanna", child.task_id) not in by_key
    assert by_key[("sakura", parent.task_id)].queue_status == "delegated"
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.REVIEW
    links = by_key[("sakura", parent.task_id)].related_tasks
    assert links[0].kind == "delegates_to"
    assert links[0].anima_name == "kanna"
    assert links[0].task_id == child.task_id
    assert links[0].title == "submitted evidence"


def test_delegated_parent_blocks_when_child_failed_without_parent_status_update(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = kanna.add_task(
        source="anima",
        original_instruction="produce final evidence",
        assignee="kanna",
        summary="produce final evidence",
        task_id="child-failed",
    )
    kanna.update_status(child.task_id, "failed", summary="FAILED: Task produced no final response")
    parent = sakura.add_delegated_task(
        original_instruction="track final evidence",
        assignee="kanna",
        summary="[delegate] track final evidence",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert by_key[("sakura", parent.task_id)].queue_status == "delegated"
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.BLOCKED


def test_delegated_parent_blocks_when_child_done_is_non_final_progress(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = kanna.add_task(
        source="anima",
        original_instruction="produce final evidence",
        assignee="kanna",
        summary="produce final evidence",
        task_id="child-progress",
    )
    kanna.update_status(
        child.task_id,
        "done",
        summary="スキーマが確認できました。列名の正確な情報が得られたので、修正版スクリプトを作成します。",
    )
    parent = sakura.add_delegated_task(
        original_instruction="track final evidence",
        assignee="kanna",
        summary="[delegate] track final evidence",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert ("kanna", child.task_id) not in by_key
    assert by_key[("sakura", parent.task_id)].queue_status == "delegated"
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.BLOCKED


def test_delegated_parent_blocks_when_child_done_is_future_action_summary(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    hikaru = _queue(tmp_path, "hikaru")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = hikaru.add_task(
        source="anima",
        original_instruction="finalize product and post completion report to Discord",
        assignee="hikaru",
        summary="finalize product",
        task_id="child-future-action",
    )
    hikaru.update_status(
        child.task_id,
        "done",
        summary=(
            "frontmatter確認OK（status=完了、submitted=2026-06-03、confirmed=false）。"
            "final evidence JSONを保存してDiscordに投稿する。"
        ),
    )
    parent = sakura.add_delegated_task(
        original_instruction="track product finalization",
        assignee="hikaru",
        summary="[delegate] track product finalization",
        deadline="1h",
        meta={"delegated_to": "hikaru", "delegated_task_id": child.task_id},
    )

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert ("hikaru", child.task_id) not in by_key
    assert by_key[("sakura", parent.task_id)].queue_status == "delegated"
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.BLOCKED


def test_delegated_parent_blocks_when_child_done_is_tool_call_summary(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = kanna.add_task(
        source="anima",
        original_instruction="produce final evidence",
        assignee="kanna",
        summary="produce final evidence",
        task_id="child-tool-only",
    )
    kanna.update_status(
        child.task_id,
        "done",
        summary="(completed 22 tool call(s): Read, Bash, Grep)",
    )
    parent = sakura.add_delegated_task(
        original_instruction="track final evidence",
        assignee="kanna",
        summary="[delegate] track final evidence",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert ("kanna", child.task_id) not in by_key
    assert by_key[("sakura", parent.task_id)].queue_status == "delegated"
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.BLOCKED


def test_duplicate_delegated_parents_to_same_active_child_are_suppressed(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = kanna.add_task(
        source="anima",
        original_instruction="produce final six-gate evidence",
        assignee="kanna",
        summary="produce final six-gate evidence",
        task_id="child-running",
    )
    kanna.update_status(child.task_id, "in_progress", summary="running final evidence")
    first = sakura.add_delegated_task(
        original_instruction="old tracking parent",
        assignee="kanna",
        summary="[delegate] old tracking parent",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )
    second = sakura.add_delegated_task(
        original_instruction="second old tracking parent",
        assignee="kanna",
        summary="[delegate] second old tracking parent",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )
    latest = sakura.add_delegated_task(
        original_instruction="latest tracking parent",
        assignee="kanna",
        summary="[delegate] latest tracking parent",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )
    sakura.update_status(
        first.task_id,
        "delegated",
        summary=f"Superseded by active Kanna retry {child.task_id}. Await final six-gate evidence.",
    )
    sakura.update_status(
        second.task_id,
        "delegated",
        summary=f"Superseded by active Kanna retry {child.task_id}. Await final six-gate evidence.",
    )

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert by_key[("kanna", child.task_id)].column == BoardColumn.RUNNING
    assert by_key[("sakura", latest.task_id)].column == BoardColumn.WAITING
    assert ("sakura", first.task_id) not in by_key
    assert ("sakura", second.task_id) not in by_key

    archived = project_all(tmp_path / "animas", store, include_archived=True)
    archived_by_key = {(task.anima_name, task.task_id): task for task in archived}
    assert archived_by_key[("sakura", first.task_id)].visibility == AttentionVisibility.ARCHIVED
    assert archived_by_key[("sakura", first.task_id)].column == BoardColumn.SUPPRESSED
    assert archived_by_key[("sakura", first.task_id)].replaced_by == f"sakura:{latest.task_id}"


def test_duplicate_blocked_delegated_parents_to_same_active_child_are_suppressed(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = kanna.add_task(
        source="anima",
        original_instruction="produce final six-gate evidence",
        assignee="kanna",
        summary="produce final six-gate evidence",
        task_id="child-running",
    )
    kanna.update_status(child.task_id, "in_progress", summary="running final evidence")
    first = sakura.add_delegated_task(
        original_instruction="old tracking parent",
        assignee="kanna",
        summary="[delegate] old tracking parent",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )
    latest = sakura.add_delegated_task(
        original_instruction="latest tracking parent",
        assignee="kanna",
        summary="[delegate] latest tracking parent",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )
    sakura.update_status(first.task_id, "blocked", summary="old stopped wrapper")
    sakura.update_status(latest.task_id, "blocked", summary="latest stopped wrapper")

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert by_key[("kanna", child.task_id)].column == BoardColumn.RUNNING
    assert by_key[("sakura", latest.task_id)].column == BoardColumn.WAITING
    assert ("sakura", first.task_id) not in by_key

    archived = project_all(tmp_path / "animas", store, include_archived=True)
    archived_by_key = {(task.anima_name, task.task_id): task for task in archived}
    assert archived_by_key[("sakura", first.task_id)].visibility == AttentionVisibility.ARCHIVED
    assert archived_by_key[("sakura", first.task_id)].column == BoardColumn.SUPPRESSED
    assert archived_by_key[("sakura", first.task_id)].replaced_by == f"sakura:{latest.task_id}"


def test_blocked_delegated_parent_stays_blocked_when_child_failed(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    kanna = _queue(tmp_path, "kanna")
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    child = kanna.add_task(
        source="anima",
        original_instruction="produce final evidence",
        assignee="kanna",
        summary="produce final evidence",
        task_id="child-failed",
    )
    kanna.update_status(child.task_id, "failed", summary="FAILED: no final response")
    parent = sakura.add_delegated_task(
        original_instruction="track final evidence",
        assignee="kanna",
        summary="[delegate] track final evidence",
        deadline="1h",
        meta={"delegated_to": "kanna", "delegated_task_id": child.task_id},
    )
    sakura.update_status(parent.task_id, "blocked", summary="child failed without final evidence")

    projected = project_all(tmp_path / "animas", store)
    by_key = {(task.anima_name, task.task_id): task for task in projected}

    assert by_key[("kanna", child.task_id)].queue_status == "failed"
    assert by_key[("kanna", child.task_id)].column == BoardColumn.BLOCKED
    assert by_key[("sakura", parent.task_id)].queue_status == "blocked"
    assert by_key[("sakura", parent.task_id)].column == BoardColumn.BLOCKED


def test_same_task_id_is_scoped_per_anima(tmp_path: Path) -> None:
    sakura = _queue(tmp_path, "sakura")
    hinata = _queue(tmp_path, "hinata")
    sakura.add_task(
        source="human",
        original_instruction="shared id",
        assignee="sakura",
        summary="sakura task",
        task_id="same",
    )
    hinata.add_task(
        source="human",
        original_instruction="shared id",
        assignee="hinata",
        summary="hinata task",
        task_id="same",
        status="in_progress",
    )

    projected = project_all(tmp_path / "animas", TaskBoardStore(tmp_path / "taskboard.sqlite3"))

    assert {(task.anima_name, task.task_id, task.column) for task in projected} == {
        ("sakura", "same", BoardColumn.TODO),
        ("hinata", "same", BoardColumn.RUNNING),
    }
