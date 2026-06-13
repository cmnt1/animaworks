from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.supervisor.ipc import IPCRequest
from core.supervisor.runner import AnimaRunner


def _make_runner(tmp_path: Path) -> AnimaRunner:
    return AnimaRunner(
        anima_name="mei",
        socket_path=tmp_path / "mei.sock",
        animas_dir=tmp_path / "animas",
        shared_dir=tmp_path / "shared",
    )


@pytest.mark.asyncio
async def test_ipc_request_cancelled_without_shutdown_returns_error(tmp_path: Path):
    runner = _make_runner(tmp_path)

    async def cancelled_handler(_params):
        raise asyncio.CancelledError()

    runner._get_handler = lambda _method: cancelled_handler  # type: ignore[method-assign]

    response = await runner._handle_request(IPCRequest(id="req1", method="process_message", params={}))

    assert response.error is not None
    assert response.error["code"] == "REQUEST_CANCELLED"
    assert not runner.shutdown_event.is_set()


@pytest.mark.asyncio
async def test_ipc_request_cancelled_during_shutdown_propagates(tmp_path: Path):
    runner = _make_runner(tmp_path)
    runner.shutdown_event.set()

    async def cancelled_handler(_params):
        raise asyncio.CancelledError()

    runner._get_handler = lambda _method: cancelled_handler  # type: ignore[method-assign]

    with pytest.raises(asyncio.CancelledError):
        await runner._handle_request(IPCRequest(id="req1", method="process_message", params={}))
