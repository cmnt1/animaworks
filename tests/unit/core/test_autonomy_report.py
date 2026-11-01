from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.schemas import TaskEntry
from core.tasks.autonomy_report import build_autonomy_report
from core.tasks.board.tasks import TaskStore, task_database_path
from core.time_utils import now_local

NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)


def _entry(task_id: str, *, source: str = "anima", assignee: str = "worker") -> TaskEntry:
    return TaskEntry(
        task_id=task_id,
        ts=NOW.isoformat(),
        source=source,  # type: ignore[arg-type]
        original_instruction=f"Instruction for {task_id}",
        assignee=assignee,
        status="pending",
        summary=task_id,
        relay_chain=[],
        updated_at=NOW.isoformat(),
        meta={},
    )


def _submit(
    store: TaskStore,
    anima: str,
    task_id: str,
    *,
    entry_source: str = "anima",
    payload_source: str = "anima",
    submitted_by: str | None = None,
    reply_to: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "task_id": task_id,
        "task_type": "llm",
        "title": task_id,
        "description": f"Instruction for {task_id}",
        "source": payload_source,
    }
    if submitted_by is not None:
        payload["submitted_by"] = submitted_by
    if reply_to is not None:
        payload["reply_to"] = reply_to
    entry = _entry(task_id, source=entry_source, assignee=anima)
    store.submit(anima, entry, payload)


def _add_attempt(store: TaskStore, anima: str, task_id: str, started_at: datetime) -> None:
    with store.transaction() as db:
        db.execute(
            "INSERT INTO task_attempts(token,anima,task_id,number,identity_json,started_at) VALUES(?,?,?,?,?,?)",
            (uuid.uuid4().hex, anima, task_id, 1, "{}", started_at.isoformat()),
        )


def _update(
    store: TaskStore,
    anima: str,
    task_id: str,
    *,
    status: str,
    updated_at: datetime | None = None,
    meta: dict | None = None,
) -> None:
    event: dict[str, object] = {
        "_event": "update",
        "task_id": task_id,
        "status": status,
        "updated_at": (updated_at or NOW).isoformat(),
    }
    if meta is not None:
        event["meta"] = meta
    store.apply(anima, event)


def _write_activity(runtime: Path, anima: str, day: str, entries: list[dict | str]) -> None:
    path = runtime / "animas" / anima / "activity_log" / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False) for entry in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _log(ts: str, event_type: str, task_id: str | None = None, **extra) -> dict:
    meta = {"task_id": task_id} if task_id else {}
    return {"ts": ts, "type": event_type, "meta": meta, **extra}


def test_classification_period_and_activity_aggregation(tmp_path):
    runtime = tmp_path / "runtime"
    worker_dir = runtime / "animas" / "worker"
    worker_dir.mkdir(parents=True)
    store = TaskStore(task_database_path(worker_dir))

    _submit(store, "worker", "self", submitted_by="worker", reply_to="worker")
    _submit(store, "worker", "reply-only", submitted_by="other", reply_to="worker")
    _submit(store, "worker", "delegated", payload_source="delegation", submitted_by="boss", reply_to="boss")
    _submit(store, "worker", "human", entry_source="human", payload_source="cli", submitted_by="worker")
    _submit(store, "worker", "unknown", payload_source="cli", submitted_by="other", reply_to="other")
    _submit(
        store,
        "worker",
        "out-of-period",
        payload_source="delegation",
        submitted_by="boss",
        reply_to="boss",
    )
    _submit(
        store,
        "worker",
        "old-cancel",
        payload_source="delegation",
        submitted_by="boss",
        reply_to="boss",
    )
    _submit(store, "worker", "bare-cancel", payload_source="cli", submitted_by="worker", reply_to="worker")
    _submit(store, "worker", "wait-1", payload_source="cli", submitted_by="worker", reply_to="worker")
    _submit(store, "worker", "done-1", payload_source="cli", submitted_by="worker", reply_to="worker")

    _add_attempt(store, "worker", "self", NOW - timedelta(days=1))
    _add_attempt(store, "worker", "reply-only", NOW - timedelta(days=2))
    _add_attempt(store, "worker", "delegated", NOW - timedelta(days=3))
    _add_attempt(store, "worker", "human", NOW - timedelta(days=4))
    _add_attempt(store, "worker", "unknown", NOW - timedelta(days=5))
    _add_attempt(store, "worker", "out-of-period", NOW - timedelta(days=8))
    _add_attempt(store, "worker", "old-cancel", NOW - timedelta(days=8))

    _update(
        store,
        "worker",
        "delegated",
        status="cancelled",
        meta={"scope_notes": [{"note": "narrowed"}, {"note": "stopped"}]},
    )
    _update(store, "worker", "bare-cancel", status="cancelled")
    _update(store, "worker", "done-1", status="done", meta={"scope_notes": [{"note": "kept"}]})
    _update(store, "worker", "wait-1", status="pending", meta={"waiting_for": "human review"})
    _update(store, "worker", "old-cancel", status="cancelled", updated_at=NOW - timedelta(days=8))

    _write_activity(
        runtime,
        "worker",
        "2026-05-09",
        [
            _log("2026-05-09T01:00:00+00:00", "heartbeat_start"),
            _log("2026-05-09T02:00:00+00:00", "cron_executed"),
            _log("2026-05-09T03:00:00+00:00", "inbox_processing_start"),
            _log("2026-05-09T04:00:00+00:00", "message_received", channel="chat"),
            _log("2026-05-09T04:30:00+00:00", "cron_executed", meta={"command": "true"}),
            _log("2026-05-09T05:00:00+00:00", "task_exec_start"),
            _log("2026-05-09T06:00:00+00:00", "message_received", task_id="delegated"),
            _log("2026-05-09T07:00:00+00:00", "message_sent", task_id="delegated"),
            _log("2026-05-09T08:00:00+00:00", "dm_sent", task_id="delegated"),
            _log("2026-05-09T09:00:00+00:00", "message_sent"),
            "not-json",
        ],
    )
    _write_activity(
        runtime,
        "worker",
        "2026-05-03",
        [
            _log("2026-05-03T11:00:00+00:00", "heartbeat_start"),
            _log("2026-05-03T13:00:00+00:00", "heartbeat_start"),
        ],
    )
    _write_activity(runtime, "worker", "2026-04-01", [_log("2026-04-01T00:00:00+00:00", "cron_executed")])

    report = build_autonomy_report(runtime, days=7, now=NOW)
    worker = report["animas"]["worker"]

    assert worker["task_starts"] == {"self": 2, "delegated": 1, "human": 1, "unknown": 1, "total": 5}
    assert worker["spontaneity_ratio"] == 0.4
    assert worker["launch_counts"] == {
        "heartbeat": 2,
        "cron": 1,
        "inbox": 1,
        "chat": 1,
        "task_exec": 1,
        "total": 6,
    }
    assert worker["discretion"] == {"delegated_cancelled": 1, "scope_notes": 3, "waiting_for": 1}
    assert worker["round_trips"] == {
        "delegated_tasks": 1,
        "event_count": 3,
        "median": 3.0,
        "max": 3,
        "top_task_ids": [{"task_id": "delegated", "count": 3}],
    }
    assert worker["cost"]["total_estimated_cost_usd"] == 0.0
    assert worker["cost"]["cost_share"] is None
    assert worker["launch_share"] == 1.0

    assert report["totals"]["task_starts"] == {
        "self": 2,
        "delegated": 1,
        "human": 1,
        "unknown": 1,
        "total": 5,
    }
    assert report["totals"]["launch_counts"]["total"] == 6
    assert report["totals"]["round_trips"]["top_task_ids"] == [{"task_id": "delegated", "count": 3, "anima": "worker"}]


def test_missing_activity_logs_and_task_store_return_zeros(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "animas" / "worker").mkdir(parents=True)

    report = build_autonomy_report(runtime, days=7, now=NOW)
    worker = report["animas"]["worker"]

    assert worker["task_starts"]["total"] == 0
    assert worker["launch_counts"]["total"] == 0
    assert worker["spontaneity_ratio"] is None
    assert worker["launch_share"] is None
    assert worker["cost"]["total_estimated_cost_usd"] == 0.0
    assert worker["cost"]["cost_share"] is None
    assert worker["round_trips"]["top_task_ids"] == []

    empty = build_autonomy_report(tmp_path / "does-not-exist", days=7, now=NOW)
    assert empty["animas"] == {}
    assert empty["totals"]["task_starts"]["total"] == 0
    assert empty["totals"]["launch_counts"]["total"] == 0


def test_anima_filter_includes_missing_directory(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "animas" / "worker").mkdir(parents=True)
    _write_activity(runtime, "worker", "2026-05-09", [_log("2026-05-09T01:00:00+00:00", "heartbeat_start")])

    report = build_autonomy_report(runtime, days=7, anima="ghost", now=NOW)
    assert list(report["animas"]) == ["ghost"]
    assert report["animas"]["ghost"]["launch_counts"]["total"] == 0
    assert report["totals"]["launch_counts"]["total"] == 0


def test_days_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        build_autonomy_report(tmp_path, days=0, now=NOW)


def test_cost_share_reuses_token_usage(tmp_path):
    runtime = tmp_path / "runtime"
    today = now_local().date().isoformat()
    for name, cost in (("worker", 1.0), ("boss", 3.0)):
        path = runtime / "animas" / name / "token_usage" / f"{today}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"ts": now_local().isoformat(), "estimated_cost_usd": cost}) + "\n",
            encoding="utf-8",
        )

    report = build_autonomy_report(runtime, days=7)

    assert report["animas"]["worker"]["cost"]["total_estimated_cost_usd"] == 1.0
    assert report["animas"]["worker"]["cost"]["cost_share"] == 0.25
    assert report["animas"]["worker"]["cost"]["cost_available"] is True
    assert report["animas"]["boss"]["cost"]["cost_share"] == 0.75
    assert report["totals"]["cost"]["total_estimated_cost_usd"] == 4.0
    assert report["totals"]["cost"]["cost_available"] is True
    assert report["totals"]["cost_share"] == 1.0


def test_dm_task_ids_falls_back_to_ctx_and_text():
    from core.tasks.autonomy_report import _dm_task_ids

    known = {"0123456789ab", "ba9876543210"}
    raw = {
        "type": "message_sent",
        "ctx": "task:feedfacecafe",
        "content": "resume 0123456789ab please, not deadbeef0000",
    }
    assert _dm_task_ids(raw, known) == {"feedfacecafe", "0123456789ab"}
    assert _dm_task_ids({"type": "message_sent", "content": "no ids"}, known) == set()
