"""Unit tests for the root/task runner IPC v2 wire contract."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from core.supervisor.ipc_v2 import (
    IPC_V2_MAX_FRAME_BYTES,
    IPCV2Connection,
    IPCV2ConnectionError,
    IPCV2ConnectionState,
    IPCV2Envelope,
    IPCV2Identity,
    IPCV2PayloadTooLarge,
    read_ipc_v2_envelope,
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


def test_envelope_round_trip(identity: IPCV2Identity) -> None:
    envelope = IPCV2Envelope(
        kind="request",
        identity=identity,
        seq=1,
        body={"request_id": "request-1", "method": "run", "params": {"task": "daily"}},
    )

    decoded = IPCV2Envelope.from_bytes(envelope.to_bytes())

    assert decoded == envelope


@pytest.mark.asyncio
async def test_request_response_acknowledges_frames(identity: IPCV2Identity) -> None:
    server_state = IPCV2ConnectionState(identity)
    server_done = asyncio.Event()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection = IPCV2Connection(reader, writer, server_state)
        request = await connection.receive()
        assert request.body["method"] == "run"
        await connection.send_response(request.body["request_id"], result={"status": "ok"})
        server_done.set()
        await asyncio.sleep(0.05)
        await connection.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    client_state = IPCV2ConnectionState(identity)
    client = IPCV2Connection(reader, writer, client_state)
    try:
        await client.send_request("request-1", "run", {})
        response = await client.receive()
        assert response.body["result"] == {"status": "ok"}
        assert client_state.last_acked_seq == 1
        assert not client_state.unacked
        await asyncio.wait_for(server_done.wait(), timeout=1)
    finally:
        await client.close()
        server.close()
        await server.wait_closed()


def test_payload_limit_is_enforced_before_send(identity: IPCV2Identity) -> None:
    envelope = IPCV2Envelope(
        kind="event",
        identity=identity,
        seq=1,
        body={"event": "progress", "data": {"value": "x" * IPC_V2_MAX_FRAME_BYTES}},
    )

    with pytest.raises(IPCV2PayloadTooLarge):
        envelope.to_bytes()


@pytest.mark.asyncio
async def test_eof_is_an_explicit_disconnect() -> None:
    reader = asyncio.StreamReader()
    reader.feed_eof()

    with pytest.raises(IPCV2ConnectionError, match="disconnected"):
        await read_ipc_v2_envelope(reader)


@pytest.mark.asyncio
async def test_connection_reset_is_an_explicit_disconnect() -> None:
    reader = asyncio.StreamReader()
    reader.readline = AsyncMock(side_effect=ConnectionResetError("reset"))

    with pytest.raises(IPCV2ConnectionError, match="disconnected"):
        await read_ipc_v2_envelope(reader)
