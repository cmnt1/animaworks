"""IPC v2 state-write queue responsiveness tests."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from core.runtime.ipc_v2 import (
    IPC_V2_MAX_FRAME_BYTES,
    IPCV2Connection,
    IPCV2ConnectionState,
    IPCV2Identity,
)
from core.runtime.task_runner_supervisor import TaskRunnerJob, TaskRunnerSupervisor


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("os").name == "nt", reason="Requires POSIX Unix socket server")
async def test_slow_state_write_does_not_block_connection_request_loop(tmp_path: Path) -> None:
    identity = IPCV2Identity(
        job_id="state-write-test",
        root_epoch=str(uuid.uuid4()),
        attempt=1,
        lane="chat",
        display_lane="chat",
    )
    loop = asyncio.get_running_loop()
    supervisor = TaskRunnerSupervisor("alice", tmp_path / "alice", tmp_path / "shared")
    job = TaskRunnerJob(
        identity=identity,
        request_id="run-contract",
        params={},
        result=loop.create_future(),
        peer_state=IPCV2ConnectionState(identity),
    )
    supervisor.jobs[identity.job_id] = job

    original_execute = supervisor._state_writer.execute_operation

    async def delayed_write(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "write_recovery_note":
            await asyncio.sleep(1.0)
        return await original_execute(operation, payload)

    supervisor._state_writer.execute_operation = delayed_write  # type: ignore[method-assign]
    socket_path = tmp_path / "state-writer.sock"
    server = await asyncio.start_unix_server(
        supervisor._handle_connection,
        path=str(socket_path),
        limit=IPC_V2_MAX_FRAME_BYTES + 1,
    )
    reader, writer = await asyncio.open_unix_connection(
        str(socket_path),
        limit=IPC_V2_MAX_FRAME_BYTES + 1,
    )
    connection = IPCV2Connection(reader, writer, IPCV2ConnectionState(identity))

    try:
        await connection.send_event(
            "hello",
            {"capabilities": {"reconnect": True, "steer": False}, "last_received_seq": 0},
        )
        while True:
            first = await asyncio.wait_for(connection.receive(), timeout=2.0)
            if first.kind == "request" and first.body["method"] == "run":
                break

        started = time.monotonic()
        await connection.send_request(
            "slow-write",
            "state_write",
            {"operation": "write_recovery_note", "payload": {"content": "durable"}},
        )
        await connection.send_request("probe", "unsupported_probe", {})

        responses: dict[str, Any] = {}
        while "probe" not in responses:
            envelope = await asyncio.wait_for(connection.receive(), timeout=2.0)
            if envelope.kind == "response":
                responses[envelope.body["request_id"]] = envelope
        probe_elapsed = time.monotonic() - started
        assert probe_elapsed < 0.75
        assert responses["probe"].body["error"]["code"] == "PROTOCOL_ERROR"

        while "slow-write" not in responses:
            envelope = await asyncio.wait_for(connection.receive(), timeout=2.0)
            if envelope.kind == "response":
                responses[envelope.body["request_id"]] = envelope
        assert responses["slow-write"].body["result"] == {}
        assert (tmp_path / "alice" / "state" / "recovery_note.md").read_text(encoding="utf-8") == "durable"
    finally:
        await connection.close()
        server.close()
        await server.wait_closed()
