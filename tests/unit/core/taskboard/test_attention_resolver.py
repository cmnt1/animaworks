from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core.taskboard.attention_resolver import (
    AttentionResolver,
    notification_key_for,
    resolver_for_anima_dir,
)
from core.taskboard.models import AttentionVisibility, BoardColumn, BoardTask
from core.taskboard.store import TaskBoardStore

NOW = datetime(2026, 5, 14, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def _task(
    *,
    visibility: AttentionVisibility = AttentionVisibility.ACTIVE,
    queue_status: str = "pending",
    task_id: str = "task123456",
    queue_updated_at: str | None = None,
    expires_at: str | None = None,
    snoozed_until: str | None = None,
    queue_missing: bool = False,
) -> BoardTask:
    return BoardTask(
        anima_name="sakura",
        task_id=task_id,
        queue_missing=queue_missing,
        source="human",
        assignee="sakura",
        queue_status=queue_status,
        summary=f"summary {task_id}",
        queue_updated_at=queue_updated_at or NOW.isoformat(),
        visibility=visibility,
        column=BoardColumn.TODO,
        expires_at=expires_at,
        snoozed_until=snoozed_until,
    )


def test_decision_matrix_for_visibility_values() -> None:
    resolver = AttentionResolver()

    assert resolver.resolve_task(_task(visibility=AttentionVisibility.ACTIVE), NOW).visible_in_prompt is True
    assert (
        resolver.resolve_task(
            _task(visibility=AttentionVisibility.SNOOZED, snoozed_until=(NOW + timedelta(hours=1)).isoformat()),
            NOW,
        ).reason
        == "snoozed"
    )
    assert resolver.resolve_task(_task(visibility=AttentionVisibility.EXPIRED), NOW).reason == "expired"
    assert resolver.resolve_task(_task(visibility=AttentionVisibility.ARCHIVED), NOW).reason == "archived"
    assert resolver.resolve_task(_task(visibility=AttentionVisibility.TOMBSTONED), NOW).reason == "tombstoned"


def test_expired_task_is_hidden_and_records_metadata(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="sakura",
        task_id="task123456",
        visibility="active",
        expires_at=(NOW - timedelta(minutes=1)).isoformat(),
    )
    resolver = AttentionResolver(store)

    decision = resolver.resolve_task(
        _task(expires_at=(NOW - timedelta(minutes=1)).isoformat()),
        NOW,
    )

    assert decision.visible_in_prompt is False
    assert decision.reason == "expired"
    assert store.get_metadata("sakura", "task123456").visibility == AttentionVisibility.EXPIRED
    assert store.list_events(anima_name="sakura", task_id="task123456")[-1]["event_type"] == "expired"


def test_snooze_elapsed_becomes_visible_and_active(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="sakura",
        task_id="task123456",
        visibility="snoozed",
        snoozed_until=(NOW - timedelta(minutes=1)).isoformat(),
    )
    resolver = AttentionResolver(store)

    decision = resolver.resolve_task(
        _task(
            visibility=AttentionVisibility.SNOOZED,
            snoozed_until=(NOW - timedelta(minutes=1)).isoformat(),
        ),
        NOW,
    )

    assert decision.visible_in_prompt is True
    assert store.get_metadata("sakura", "task123456").visibility == AttentionVisibility.ACTIVE


def test_should_execute_runtime_decisions(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    resolver = AttentionResolver(store)

    store.upsert_metadata(anima_name="sakura", task_id="archived1234", visibility="archived")
    assert resolver.should_execute("sakura", "archived1234", queue_status="pending", now=NOW).executable is False
    assert resolver.should_execute("sakura", "archived1234", queue_status="pending", now=NOW).reason == "archived"

    store.upsert_metadata(
        anima_name="sakura",
        task_id="snoozed1234",
        visibility="snoozed",
        snoozed_until=(NOW + timedelta(hours=1)).isoformat(),
    )
    assert resolver.should_execute("sakura", "snoozed1234", queue_status="pending", now=NOW).reason == "snoozed"

    store.upsert_metadata(
        anima_name="sakura",
        task_id="elapsed1234",
        visibility="snoozed",
        snoozed_until=(NOW - timedelta(minutes=1)).isoformat(),
    )
    assert resolver.should_execute("sakura", "elapsed1234", queue_status="pending", now=NOW).executable is True
    assert store.get_metadata("sakura", "elapsed1234").visibility == AttentionVisibility.ACTIVE

    store.upsert_metadata(
        anima_name="sakura",
        task_id="terminal_elapsed1234",
        visibility="snoozed",
        snoozed_until=(NOW - timedelta(minutes=1)).isoformat(),
    )
    terminal_elapsed = resolver.should_execute("sakura", "terminal_elapsed1234", queue_status="done", now=NOW)
    assert terminal_elapsed.executable is False
    assert terminal_elapsed.reason == "terminal"

    assert resolver.should_execute("sakura", "done1234", queue_status="done", now=NOW).reason == "terminal"


def test_terminal_and_missing_tasks_are_hidden() -> None:
    resolver = AttentionResolver()

    assert resolver.resolve_task(_task(queue_status="done"), NOW).reason == "terminal"
    assert resolver.resolve_task(_task(queue_status="cancelled"), NOW).reason == "terminal"
    assert resolver.resolve_task(_task(queue_missing=True), NOW).reason == "queue_missing"


def test_failed_task_review_window() -> None:
    resolver = AttentionResolver()

    recent = resolver.resolve_task(
        _task(queue_status="failed", queue_updated_at=(NOW - timedelta(days=6, hours=23)).isoformat()),
        NOW,
    )
    old = resolver.resolve_task(
        _task(queue_status="failed", queue_updated_at=(NOW - timedelta(days=8)).isoformat()),
        NOW,
    )

    assert recent.visible_in_prompt is True
    assert recent.reason == "failed_review_window"
    assert old.visible_in_prompt is False
    assert old.reason == "failed_stale"


def test_invalid_datetime_metadata_is_treated_as_active() -> None:
    resolver = AttentionResolver()

    invalid_snooze = resolver.resolve_task(
        _task(visibility=AttentionVisibility.SNOOZED, snoozed_until="not-a-date"),
        NOW,
    )
    invalid_expiry = resolver.resolve_task(_task(expires_at="not-a-date"), NOW)

    assert invalid_snooze.visible_in_prompt is True
    assert invalid_snooze.reason == "active"
    assert invalid_expiry.visible_in_prompt is True
    assert invalid_expiry.reason == "active"


def test_should_show_task_result_suppressed_and_old_unmapped(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    store.upsert_metadata(anima_name="sakura", task_id="hidden1234", visibility="tombstoned")
    resolver = AttentionResolver(store)

    assert resolver.should_show_task_result("sakura", "hidden1234", NOW.timestamp(), NOW) is False
    assert (
        resolver.should_show_task_result(
            "sakura",
            "orphan1234",
            (NOW - timedelta(hours=25)).timestamp(),
            NOW,
        )
        is False
    )
    assert (
        resolver.should_show_task_result(
            "sakura",
            "orphan1234",
            (NOW - timedelta(hours=1)).timestamp(),
            NOW,
        )
        is True
    )


def test_should_show_human_notify_suppresses_same_key_for_24h(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")
    key = notification_key_for("", "same body")
    store.upsert_metadata(
        anima_name="sakura",
        task_id="task123456",
        notification_key=key,
        last_notified_at=(NOW - timedelta(hours=2)).isoformat(),
    )
    resolver = AttentionResolver(store)

    assert resolver.should_show_human_notify("sakura", key, NOW.isoformat(), NOW) is False
    assert resolver.should_show_human_notify("sakura", notification_key_for("", "new body"), NOW.isoformat(), NOW)


def test_current_state_freshness_and_suppressed_refs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    (anima_dir / "state").mkdir(parents=True)
    state_path = anima_dir / "state" / "current_state.md"
    state_path.write_text("status: working\narchive abc12345\nkeep live task\n", encoding="utf-8")

    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    store.upsert_metadata(anima_name="sakura", task_id="abc12345", visibility="archived")
    resolver = resolver_for_anima_dir(anima_dir)

    assert resolver.should_inject_current_state(anima_dir, NOW) is True
    filtered = resolver.filter_current_state(anima_dir, state_path.read_text(encoding="utf-8"), NOW)
    assert "abc12345" not in filtered
    assert "keep live task" in filtered

    old = (NOW - timedelta(hours=25)).timestamp()
    os.utime(state_path, (old, old))
    assert resolver.should_inject_current_state(anima_dir, NOW) is False


def test_current_state_filters_short_task_id_substrings(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    (anima_dir / "state").mkdir(parents=True)
    state = "\n".join(
        [
            "status: working",
            "remove shortened abcdef12",
            "remove aw ref aw://task/sakura/abcdef12",
            "keep live note",
        ]
    )
    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    store.upsert_metadata(anima_name="sakura", task_id="abcdef123456", visibility="archived")
    resolver = resolver_for_anima_dir(anima_dir)

    filtered = resolver.filter_current_state(anima_dir, state, NOW)

    assert "abcdef12" not in filtered
    assert "aw://task" not in filtered
    assert "keep live note" in filtered
