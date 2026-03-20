"""
Transport helpers for IPC server/client communication.
"""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_TCP_LOOPBACK_HOST = "127.0.0.1"
_TCP_METADATA_VERSION = 1
_ALLOWED_LOOPBACK = frozenset({ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")})


@dataclass(frozen=True)
class IPCTransportEndpoint:
    """Resolved IPC endpoint for either Unix socket or loopback TCP."""

    transport: str
    socket_path: Path
    host: str | None = None
    port: int | None = None

    def describe(self) -> str:
        if self.transport == "tcp":
            return f"tcp://{self.host}:{self.port}"
        return str(self.socket_path)


def _transport_override() -> str:
    value = os.environ.get("ANIMAWORKS_IPC_TRANSPORT", "auto").strip().lower()
    if value in {"auto", "unix", "tcp"}:
        return value
    logger.warning("Ignoring invalid ANIMAWORKS_IPC_TRANSPORT=%r", value)
    return "auto"


def should_use_tcp_transport() -> bool:
    """Return whether the server side should expose TCP transport."""
    override = _transport_override()
    if override == "tcp":
        return True
    if override == "unix":
        return False
    return os.name == "nt"


def cleanup_ipc_endpoint(socket_path: Path) -> None:
    """Remove a stale IPC endpoint file if present."""
    try:
        if socket_path.exists():
            socket_path.unlink()
    except OSError:
        logger.debug("Failed to remove IPC endpoint %s", socket_path, exc_info=True)


def _read_tcp_metadata(socket_path: Path) -> IPCTransportEndpoint | None:
    if not socket_path.is_file():
        return None
    try:
        data = json.loads(socket_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    if data.get("transport") != "tcp":
        return None
    host = str(data.get("host") or _TCP_LOOPBACK_HOST)
    try:
        if ipaddress.ip_address(host) not in _ALLOWED_LOOPBACK:
            logger.warning("Ignoring non-loopback IPC host %r in %s", host, socket_path)
            return None
    except ValueError:
        logger.warning("Ignoring invalid IPC host %r in %s", host, socket_path)
        return None
    port = int(data["port"])
    return IPCTransportEndpoint(
        transport="tcp",
        socket_path=socket_path,
        host=host,
        port=port,
    )


def resolve_client_endpoint(socket_path: Path) -> IPCTransportEndpoint:
    """Resolve the current client connection target from the socket path."""
    tcp_endpoint = _read_tcp_metadata(socket_path)
    if tcp_endpoint is not None:
        return tcp_endpoint
    return IPCTransportEndpoint(transport="unix", socket_path=socket_path)


def _write_tcp_metadata(socket_path: Path, endpoint: IPCTransportEndpoint) -> None:
    payload = {
        "version": _TCP_METADATA_VERSION,
        "transport": "tcp",
        "host": endpoint.host,
        "port": endpoint.port,
    }
    socket_path.write_text(json.dumps(payload), encoding="utf-8")


async def start_ipc_server(
    socket_path: Path,
    handler,
    *,
    limit: int,
) -> tuple[asyncio.Server, IPCTransportEndpoint]:
    """Start an IPC listener and return the active endpoint."""
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_ipc_endpoint(socket_path)

    if should_use_tcp_transport():
        server = await asyncio.start_server(
            handler,
            host=_TCP_LOOPBACK_HOST,
            port=0,
            limit=limit,
        )
        sockets = server.sockets or []
        if not sockets:
            server.close()
            await server.wait_closed()
            raise RuntimeError("TCP IPC server started without bound sockets")
        host, port = sockets[0].getsockname()[:2]
        endpoint = IPCTransportEndpoint(
            transport="tcp",
            socket_path=socket_path,
            host=str(host),
            port=int(port),
        )
        try:
            _write_tcp_metadata(socket_path, endpoint)
        except Exception:
            server.close()
            await server.wait_closed()
            raise
        return server, endpoint

    server = await asyncio.start_unix_server(
        handler,
        path=str(socket_path),
        limit=limit,
    )
    return server, IPCTransportEndpoint(
        transport="unix",
        socket_path=socket_path,
    )


async def open_ipc_connection(
    socket_path: Path,
    *,
    limit: int,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open a client connection to the current IPC endpoint."""
    endpoint = resolve_client_endpoint(socket_path)
    if endpoint.transport == "tcp":
        if endpoint.port is None:
            raise ConnectionError(f"TCP IPC metadata missing port: {socket_path}")
        return await asyncio.open_connection(
            host=endpoint.host or _TCP_LOOPBACK_HOST,
            port=endpoint.port,
            limit=limit,
        )
    if not hasattr(asyncio, "open_unix_connection"):
        raise FileNotFoundError(f"Unix IPC transport is unavailable on this platform: {socket_path}")
    return await asyncio.open_unix_connection(
        path=str(socket_path),
        limit=limit,
    )
