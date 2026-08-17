"""End-to-end regression coverage for IPC stream disconnect cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from core.supervisor.ipc import IPCRequest, IPCResponse, IPCServer


@pytest.mark.asyncio
async def test_server_closes_stream_when_client_disconnects(tmp_path):
    socket_path = tmp_path / "disconnect.sock"
    continue_stream = asyncio.Event()
    stream_closed = asyncio.Event()
    streams: list[AsyncIterator[IPCResponse]] = []

    async def handler(request: IPCRequest) -> AsyncIterator[IPCResponse]:
        async def _gen() -> AsyncIterator[IPCResponse]:
            try:
                yield IPCResponse(id=request.id, stream=True, chunk="first")
                await continue_stream.wait()
                yield IPCResponse(id=request.id, stream=True, chunk="x" * (2 * 1024 * 1024))
            finally:
                stream_closed.set()

        stream = _gen()
        streams.append(stream)  # Keep it alive so GC cannot hide a missing explicit close.
        return stream

    server = IPCServer(socket_path, handler)
    await server.start()

    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        request = IPCRequest(id="disconnect_001", method="stream_test")
        writer.write((request.to_json() + "\n").encode())
        await writer.drain()
        assert IPCResponse.from_json((await reader.readline()).decode()).chunk == "first"

        writer.transport.abort()
        continue_stream.set()

        await asyncio.wait_for(stream_closed.wait(), timeout=2.0)
    finally:
        continue_stream.set()
        if streams:
            await streams[0].aclose()
        await server.stop()
