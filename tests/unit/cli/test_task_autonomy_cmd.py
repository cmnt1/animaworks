from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.commands.task_cmd import register_task_command
from core.schemas import TaskEntry
from core.tasks.board.tasks import TaskStore, task_database_path
from core.time_utils import now_local


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    worker_dir = runtime_dir / "animas" / "worker"
    worker_dir.mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(runtime_dir))
    monkeypatch.delenv("ANIMAWORKS_ANIMA_DIR", raising=False)
    return runtime_dir, worker_dir


def _invoke(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register_task_command(subparsers)
    args = parser.parse_args(["task", *argv])
    args.func(args)


def _worker_task(worker_dir: Path, task_id: str) -> None:
    now = datetime.now(UTC)
    store = TaskStore(task_database_path(worker_dir))
    entry = TaskEntry(
        task_id=task_id,
        ts=now.isoformat(),
        source="anima",
        original_instruction="Do the work",
        assignee="worker",
        status="pending",
        summary=task_id,
        relay_chain=[],
        updated_at=now.isoformat(),
        meta={},
    )
    store.submit(
        "worker",
        entry,
        {
            "task_id": task_id,
            "title": task_id,
            "description": "Do the work",
            "source": "anima",
            "submitted_by": "worker",
            "reply_to": "worker",
        },
    )
    with store.transaction() as db:
        db.execute(
            "INSERT INTO task_attempts(token,anima,task_id,number,identity_json,started_at) VALUES(?,?,?,?,?,?)",
            (uuid.uuid4().hex, "worker", task_id, 1, "{}", (now - timedelta(days=1)).isoformat()),
        )


def _write_activity(worker_dir: Path, entries: list[dict]) -> None:
    day = now_local().date().isoformat()
    path = worker_dir / "activity_log" / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def test_autonomy_json_has_per_anima_and_totals(runtime, capsys):
    _, worker_dir = runtime
    _worker_task(worker_dir, "cli-task")
    _write_activity(
        worker_dir,
        [
            {"ts": now_local().isoformat(), "type": "heartbeat_start", "meta": {}},
            {"ts": now_local().isoformat(), "type": "message_sent", "meta": {"task_id": "cli-task"}},
        ],
    )

    _invoke(["autonomy", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["days"] == 7
    assert "worker" in payload["animas"]
    assert payload["animas"]["worker"]["task_starts"]["self"] == 1
    assert payload["animas"]["worker"]["launch_counts"]["heartbeat"] == 1
    assert payload["totals"]["task_starts"]["total"] == 1
    assert payload["totals"]["launch_counts"]["total"] == 1
    assert payload["totals"]["round_trips"]["top_task_ids"] == [{"task_id": "cli-task", "count": 1, "anima": "worker"}]
    assert payload["since"] < payload["until"]


def test_autonomy_table_and_anima_filter(runtime, capsys):
    _, worker_dir = runtime
    _worker_task(worker_dir, "cli-task")
    _write_activity(
        worker_dir,
        [
            {"ts": now_local().isoformat(), "type": "message_sent", "meta": {"task_id": "cli-task"}},
        ],
    )

    _invoke(["autonomy", "--days", "3", "--anima", "worker"])
    out = capsys.readouterr().out

    assert "| worker |" in out
    assert "cli-task" in out
    assert "| 1 |" in out


def test_autonomy_missing_runtime_is_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "missing-runtime"))
    monkeypatch.delenv("ANIMAWORKS_ANIMA_DIR", raising=False)

    _invoke(["autonomy", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["animas"] == {}
    assert payload["totals"]["task_starts"]["total"] == 0
    assert payload["totals"]["launch_counts"]["total"] == 0


def test_autonomy_rejects_non_positive_days(runtime, capsys):
    with pytest.raises(SystemExit) as exc:
        _invoke(["autonomy", "--days", "0"])
    assert exc.value.code == 2
    assert "1" in capsys.readouterr().err
