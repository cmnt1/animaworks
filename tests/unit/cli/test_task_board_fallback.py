"""Sandboxed animas cannot write the task DB; board writes go through the host."""

from __future__ import annotations

import argparse
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from cli.commands.task_cmd import register_task_command
from core.memory.task_queue import TaskQueueManager


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    animas = runtime_dir / "animas"
    for name in ("worker", "boss"):
        (animas / name).mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(runtime_dir))
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(animas / "worker"))
    queue = TaskQueueManager(animas / "worker")
    queue.add_task(source="human", original_instruction="x", assignee="worker", summary="x", task_id="t1")
    return queue


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _invoke(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    register_task_command(parser.add_subparsers())
    args = parser.parse_args(["task", *argv])
    args.func(args)


def test_readonly_db_proxies_action_to_host(runtime, capsys):
    response = MagicMock()
    response.json.return_value = {"ok": True, "result": {"ok": True, "message": "Lease acquired for worker/t1"}}
    with (
        patch(
            "core.taskboard.tasks.TaskStore.acquire_lease",
            side_effect=sqlite3.OperationalError("attempt to write a readonly database"),
        ),
        patch("httpx.post", return_value=response) as post,
    ):
        _invoke(["claim", "t1"])
    assert post.call_args.args[0].endswith("/api/internal/task-board-action")
    payload = post.call_args.kwargs["json"]
    assert payload == {"actor": "worker", "action": "claim", "task_id": "t1", "ttl_seconds": 1800, "text": None}
    assert "Lease acquired" in capsys.readouterr().out


def test_host_refusal_keeps_cli_exit_code(runtime, capsys):
    response = MagicMock()
    response.json.return_value = {"ok": False, "error": "claim a lease first", "exit_code": 2, "payload": None}
    with (
        patch(
            "core.taskboard.tasks.TaskStore.acquire_lease",
            side_effect=sqlite3.OperationalError("attempt to write a readonly database"),
        ),
        patch("httpx.post", return_value=response),
        pytest.raises(SystemExit) as exit_info,
    ):
        _invoke(["claim", "t1"])
    assert exit_info.value.code == 2
    assert "claim a lease first" in capsys.readouterr().err


@pytest.mark.anyio
async def test_internal_endpoint_applies_lease_rules(runtime) -> None:
    from fastapi import FastAPI

    from server.routes.internal import create_internal_router

    app = FastAPI()
    app.state.ws_manager = MagicMock()
    app.include_router(create_internal_router(), prefix="/api")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        refused = await client.post(
            "/api/internal/task-board-action",
            json={"actor": "boss", "action": "cancel", "task_id": "t1", "text": "stale"},
        )
        claimed = await client.post(
            "/api/internal/task-board-action",
            json={"actor": "boss", "action": "claim", "task_id": "t1", "ttl_seconds": 600},
        )
        with patch("core.taskboard.board_actions.notify_task_owner", return_value=None):
            cancelled = await client.post(
                "/api/internal/task-board-action",
                json={"actor": "boss", "action": "cancel", "task_id": "t1", "text": "stale"},
            )
    assert refused.json()["ok"] is False and refused.json()["exit_code"] == 2
    assert claimed.json()["ok"] is True
    assert cancelled.json()["result"]["status"] == "cancelled"
    assert runtime.get_task_by_id("t1").status == "cancelled"


def _delegated_task(runtime) -> None:
    runtime.add_task(
        source="anima",
        original_instruction="verify",
        assignee="worker",
        summary="verify",
        task_id="t2",
        relay_chain=["boss"],
    )


def test_owner_cancel_notifies_delegator(runtime) -> None:
    from core.taskboard.board_actions import run_board_action

    _delegated_task(runtime)
    with patch("core.taskboard.board_actions._send_task_notice", return_value=None) as send:
        result = run_board_action(actor="worker", action="cancel", task_id="t2", text="blocked on human")
    assert result["status"] == "cancelled"
    send.assert_called_once_with("worker", "boss", "t2", "cancel", "blocked on human", owner="worker")


def test_delegator_cancel_notifies_owner_only(runtime) -> None:
    from core.taskboard.board_actions import run_board_action

    _delegated_task(runtime)
    run_board_action(actor="boss", action="claim", task_id="t2", ttl_seconds=600)
    with patch("core.taskboard.board_actions._send_task_notice", return_value=None) as send:
        run_board_action(actor="boss", action="cancel", task_id="t2", text="superseded")
    send.assert_called_once_with("boss", "worker", "t2", "cancel", "superseded")


def test_owner_note_does_not_notify_delegator(runtime) -> None:
    from core.taskboard.board_actions import run_board_action

    _delegated_task(runtime)
    with patch("core.taskboard.board_actions._send_task_notice", return_value=None) as send:
        run_board_action(actor="worker", action="note", task_id="t2", text="progress")
    send.assert_not_called()


def test_bulk_triage_sends_one_digest_per_recipient(runtime) -> None:
    from core.taskboard.board_actions import run_board_action
    from core.taskboard.notices import flush_task_notices

    for i in range(8):
        runtime.add_task(
            source="anima",
            original_instruction="v",
            assignee="worker",
            summary="v",
            task_id=f"b{i}",
            relay_chain=["boss"],
        )
        run_board_action(actor="boss", action="claim", task_id=f"b{i}", ttl_seconds=600)
        run_board_action(actor="boss", action="cancel", task_id=f"b{i}", text=f"merged into weekly {i}")

    with patch("core.taskboard.notices._send_digest", return_value=True) as send:
        assert flush_task_notices(quiet_seconds=3600) == 0
        assert flush_task_notices(quiet_seconds=0) == 1
    actor, to, records = send.call_args.args
    assert (actor, to) == ("boss", "worker")
    assert [r["target"] for r in records] == [f"b{i}" for i in range(8)]
    with patch("core.taskboard.notices._send_digest", return_value=True) as send:
        assert flush_task_notices(quiet_seconds=0) == 0


def test_failed_digest_is_retried(runtime) -> None:
    from core.taskboard.notices import flush_task_notices, queue_task_notice

    queue_task_notice("worker", "boss", "t2", "cancel", "blocked", owner="worker")
    with patch("core.taskboard.notices._send_digest", return_value=False):
        assert flush_task_notices(quiet_seconds=0) == 0
    with patch("core.taskboard.notices._send_digest", return_value=True) as send:
        assert flush_task_notices(quiet_seconds=0) == 1
    assert send.call_args.args[2][0]["target"] == "worker/t2"


def test_digest_reaches_recipient_inbox(runtime) -> None:
    from core.paths import get_shared_dir
    from core.taskboard.notices import flush_task_notices, queue_task_notice

    for i in range(10):
        queue_task_notice("boss", "worker", f"x{i}", "cancel", "superseded")
    assert flush_task_notices(quiet_seconds=0) == 1
    inbox = [p for p in (get_shared_dir() / "inbox" / "worker").glob("*.json")]
    assert len(inbox) == 1
    assert "boss changed 10 task(s)" in inbox[0].read_text(encoding="utf-8")
