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
