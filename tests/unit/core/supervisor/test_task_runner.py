"""Unit tests for the disposable task runner execution lifecycle."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.supervisor import task_runner
from core.supervisor.ipc_v2 import IPCV2Envelope, IPCV2Identity


class FakeConnection:
    def __init__(self) -> None:
        self.responses: list[tuple[str, dict | None, dict | None]] = []
        self.closed = False

    async def send_event(self, event: str, data: dict | None = None) -> int:
        return 1

    async def send_response(
        self,
        request_id: str,
        *,
        result: dict | None = None,
        error: dict | None = None,
    ) -> int:
        self.responses.append((request_id, result, error))
        return 2

    async def receive(self) -> IPCV2Envelope:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def close(self) -> None:
        self.closed = True


def _contract(identity: IPCV2Identity) -> IPCV2Envelope:
    return IPCV2Envelope(
        kind="request",
        identity=identity,
        seq=2,
        body={
            "request_id": "run-1",
            "method": "run",
            "params": {
                "environment": {"urls": {"ANIMAWORKS_EMBED_URL": "http://embed.test"}},
                "task": {
                    "name": "daily",
                    "schedule": "0 9 * * *",
                    "type": "llm",
                    "description": "run daily",
                }
            },
        },
    )


@pytest.fixture
def identity() -> IPCV2Identity:
    return IPCV2Identity(
        job_id="job-1",
        root_epoch=str(uuid.uuid4()),
        attempt=1,
        lane="cron",
        display_lane="background",
    )


@pytest.fixture
def args() -> argparse.Namespace:
    return argparse.Namespace(anima="sakura", lane="cron", job="job-1")


@pytest.mark.asyncio
async def test_normal_execution_returns_result_and_exit_zero(
    monkeypatch: pytest.MonkeyPatch,
    identity: IPCV2Identity,
    args: argparse.Namespace,
) -> None:
    monkeypatch.setenv("ANIMAWORKS_EMBED_URL", "http://embed.test")
    connection = FakeConnection()
    monkeypatch.setattr(
        task_runner,
        "_connect",
        AsyncMock(return_value=(connection, _contract(identity))),
    )
    monkeypatch.setattr(task_runner, "DigitalAnima", lambda **kwargs: object())
    monkeypatch.setattr(
        task_runner,
        "execute_cron_contract",
        AsyncMock(return_value={"task_type": "llm", "result": {"summary": "done"}, "success": True}),
    )

    exit_code = await task_runner.run_task(args, Path("/tmp/task.sock"), identity)

    assert exit_code == 0
    assert connection.responses == [
        (
            "run-1",
            {"task_type": "llm", "result": {"summary": "done"}, "success": True},
            None,
        )
    ]
    assert connection.closed


@pytest.mark.asyncio
async def test_execution_exception_returns_error_result(
    monkeypatch: pytest.MonkeyPatch,
    identity: IPCV2Identity,
    args: argparse.Namespace,
) -> None:
    monkeypatch.setenv("ANIMAWORKS_EMBED_URL", "http://embed.test")
    connection = FakeConnection()
    monkeypatch.setattr(
        task_runner,
        "_connect",
        AsyncMock(return_value=(connection, _contract(identity))),
    )
    monkeypatch.setattr(task_runner, "DigitalAnima", lambda **kwargs: object())
    monkeypatch.setattr(
        task_runner,
        "execute_cron_contract",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    exit_code = await task_runner.run_task(args, Path("/tmp/task.sock"), identity)

    assert exit_code == 1
    error = connection.responses[0][2]
    assert error == {"code": "EXECUTION_ERROR", "message": "boom", "retryable": False}


def test_missing_embed_url_fails_closed(monkeypatch: pytest.MonkeyPatch, args: argparse.Namespace) -> None:
    monkeypatch.delenv("ANIMAWORKS_EMBED_URL", raising=False)

    with pytest.raises(RuntimeError, match="ANIMAWORKS_EMBED_URL"):
        task_runner._required_environment(args)
