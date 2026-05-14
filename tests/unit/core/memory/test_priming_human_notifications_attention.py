from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from core.memory.priming import PrimingEngine
from core.taskboard.attention_resolver import notification_key_for
from core.taskboard.store import TaskBoardStore
from core.time_utils import now_iso, now_local


def _write_activity(anima_dir: Path, entries: list[dict]) -> None:
    log_dir = anima_dir / "activity_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = entries[0]["ts"][:10] if entries else "2026-05-14"
    path = log_dir / f"{date_str}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@pytest.mark.asyncio
async def test_human_notify_suppresses_same_notification_key_for_24h(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "rin"
    (anima_dir / "activity_log").mkdir(parents=True)
    body = "Please check deployment."
    key = notification_key_for("", body)
    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="rin",
        task_id="task123456",
        notification_key=key,
        last_notified_at=(now_local() - timedelta(hours=1)).isoformat(),
    )
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": body,
                "via": "slack",
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert result == ""


@pytest.mark.asyncio
async def test_human_notify_suppresses_subject_body_key_from_activity_meta(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "rin"
    (anima_dir / "activity_log").mkdir(parents=True)
    subject = "Deploy check"
    body = "Please check deployment."
    key = notification_key_for(subject, body)
    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="rin",
        task_id="task123456",
        notification_key=key,
        last_notified_at=(now_local() - timedelta(hours=1)).isoformat(),
    )
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": body,
                "via": "configured_channels",
                "meta": {"subject": subject, "notification_key": key},
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert result == ""


@pytest.mark.asyncio
async def test_human_notify_allows_new_body(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "rin"
    (anima_dir / "activity_log").mkdir(parents=True)
    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="rin",
        task_id="task123456",
        notification_key=notification_key_for("", "old body"),
        last_notified_at=(now_local() - timedelta(hours=1)).isoformat(),
    )
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": "new body",
                "via": "slack",
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert "new body" in result


@pytest.mark.asyncio
async def test_human_notify_gate_fails_open_when_taskboard_db_is_corrupt(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "rin"
    (anima_dir / "activity_log").mkdir(parents=True)
    shared_dir = data_dir / "shared"
    shared_dir.mkdir()
    (shared_dir / "taskboard.sqlite3").write_text("not sqlite", encoding="utf-8")
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": "surface despite corrupt db",
                "via": "slack",
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert "surface despite corrupt db" in result
