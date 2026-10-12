# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""SSM Session Manager port-forward tunnels for enclave SQL sources.

Each configured source owns a single tunnel (a child
``session-manager-plugin`` process bound to a loopback port).  Tunnels are
reused while alive, re-established when the process has died, and shut down
after ``idle_shutdown_s`` of inactivity or at interpreter exit.  AWS
credentials are obtained from the secrets store and never placed on the
plugin's command line.
"""

from __future__ import annotations

import atexit
import json
import logging
import socket
import subprocess
import threading
import time
from typing import Any

from core.enclave.config import EnclaveSsmTunnelConfig
from core.enclave.secrets import read_enclave_secret

logger = logging.getLogger(__name__)

_PLUGIN_WAIT_TIMEOUT_S = 30.0
_DOCUMENT_NAME = "AWS-StartPortForwardingSessionToRemoteHost"


class TunnelError(RuntimeError):
    """Raised when an SSM tunnel cannot be established or kept alive."""


class _Tunnel:
    __slots__ = ("config", "local_port", "process", "session", "last_used", "ssm")

    def __init__(
        self, config: EnclaveSsmTunnelConfig, local_port: int, process: subprocess.Popen, session: dict[str, Any]
    ) -> None:
        self.config = config
        self.local_port = local_port
        self.process = process
        self.session = session
        self.last_used = time.monotonic()
        self.ssm: Any = None


_LOCKS: dict[str, threading.Lock] = {}
_TUNNELS: dict[str, _Tunnel] = {}
_REAPER_STARTED = False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def _resolve_target(ec2: Any, config: EnclaveSsmTunnelConfig) -> str:
    if config.target_instance_id:
        return config.target_instance_id
    assert config.target_tag_name is not None  # enforced by the config model
    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [config.target_tag_name]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    instances = [
        instance for reservation in response.get("Reservations", []) for instance in reservation.get("Instances", [])
    ]
    if not instances:
        raise TunnelError("no running instance matched the configured target tag")
    if len(instances) > 1:
        raise TunnelError("more than one running instance matched the configured target tag")
    return instances[0]["InstanceId"]


def _read_aws_credentials(config: EnclaveSsmTunnelConfig) -> dict[str, str]:
    raw = read_enclave_secret(config.aws_secret)
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise TunnelError("the configured AWS secret is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TunnelError("the configured AWS secret must be a JSON object")
    access_key = payload.get("aws_access_key_id")
    secret_key = payload.get("aws_secret_access_key")
    if not isinstance(access_key, str) or not access_key or not isinstance(secret_key, str) or not secret_key:
        raise TunnelError("the configured AWS secret must contain aws_access_key_id and aws_secret_access_key")
    return {"aws_access_key_id": access_key, "aws_secret_access_key": secret_key}


def _start_session(
    config: EnclaveSsmTunnelConfig,
    credentials: dict[str, str],
    local_port: int,
    remote_host: str,
    remote_port: int,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Start an SSM session; return ``(session, request, ssm_client)``."""
    import boto3

    boto_session = boto3.Session(region_name=config.region, **credentials)
    ssm = boto_session.client("ssm", region_name=config.region)
    target = _resolve_target(boto_session.client("ec2", region_name=config.region), config)
    request = {
        "Target": target,
        "DocumentName": _DOCUMENT_NAME,
        "Parameters": {
            "host": [remote_host],
            "portNumber": [str(remote_port)],
            "localPortNumber": [str(local_port)],
        },
    }
    response = ssm.start_session(**request)
    if not isinstance(response, dict):
        raise TunnelError("SSM start_session returned an invalid response")
    return response, request, ssm


def _plugin_command(config: EnclaveSsmTunnelConfig, session: dict[str, Any], request: dict[str, Any]) -> list[str]:
    """Build the session-manager-plugin command line (no AWS keys on it).

    Mirrors what the AWS CLI passes: the start_session response, the region,
    the operation name, an empty profile, the original request and the endpoint.
    """
    response = {key: session.get(key) for key in ("SessionId", "TokenValue", "StreamUrl")}
    return [
        config.plugin_path,
        json.dumps(response),
        config.region,
        "StartSession",
        "",
        json.dumps(request),
        f"https://ssm.{config.region}.amazonaws.com",
    ]


def _start_plugin(config: EnclaveSsmTunnelConfig, session: dict[str, Any], request: dict[str, Any]) -> subprocess.Popen:
    process = subprocess.Popen(
        _plugin_command(config, session, request), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return process


def _wait_for_port(port: int, timeout: float = _PLUGIN_WAIT_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(port):
            return
        time.sleep(0.1)
    raise TunnelError("the port-forward tunnel did not become reachable within the timeout")


def _lock_for(name: str) -> threading.Lock:
    lock = _LOCKS.get(name)
    if lock is None:
        lock = threading.Lock()
        _LOCKS[name] = lock
    return lock


def _is_idle(tunnel: _Tunnel) -> bool:
    return time.monotonic() - tunnel.last_used > tunnel.config.idle_shutdown_s


def _is_alive(tunnel: _Tunnel) -> bool:
    return tunnel.process.poll() is None and _port_open(tunnel.local_port)


def ensure_tunnel(
    source_name: str,
    config: EnclaveSsmTunnelConfig,
    remote_host: str,
    remote_port: int,
) -> int:
    """Return the loopback port for *source_name*, creating or reusing its tunnel.

    A dead or idle tunnel is torn down and re-established.  This function is
    safe to call from multiple threads.
    """
    with _lock_for(source_name):
        _ensure_reaper()
        current = _TUNNELS.get(source_name)
        if current is not None and _is_alive(current) and not _is_idle(current):
            current.last_used = time.monotonic()
            return current.local_port

        if current is not None:
            _stop_tunnel(current)

        credentials = _read_aws_credentials(config)
        local_port = config.local_port or _free_port()
        session, request, ssm = _start_session(config, credentials, local_port, remote_host, remote_port)
        process = _start_plugin(config, session, request)
        tunnel = _Tunnel(config, local_port, process, session)
        tunnel.ssm = ssm
        _TUNNELS[source_name] = tunnel
        try:
            _wait_for_port(local_port)
        except TunnelError:
            _stop_tunnel(tunnel)
            _TUNNELS.pop(source_name, None)
            raise
        tunnel.last_used = time.monotonic()
        logger.info(
            "Established SSM tunnel for enclave source %s (port %d, pid %s)",
            source_name,
            local_port,
            tunnel.process.pid,
        )
        return local_port


def _stop_tunnel(tunnel: _Tunnel) -> None:
    session_id = tunnel.session.get("SessionId")
    if tunnel.ssm is not None and session_id:
        try:
            tunnel.ssm.terminate_session(SessionId=session_id)
        except Exception:  # noqa: BLE001 - best-effort; the session also times out server-side
            logger.debug("Could not terminate SSM session", exc_info=True)
    try:
        tunnel.process.terminate()
    except OSError:
        pass
    try:
        tunnel.process.wait(timeout=5)
    except Exception:  # noqa: BLE001 - best-effort cleanup
        try:
            tunnel.process.kill()
        except OSError:
            pass


def stop_tunnel(source_name: str) -> None:
    """Stop and forget the tunnel for *source_name* (if any)."""
    with _lock_for(source_name):
        tunnel = _TUNNELS.pop(source_name, None)
        if tunnel is not None:
            _stop_tunnel(tunnel)
            logger.info("Stopped SSM tunnel for enclave source %s", source_name)


def stop_idle_tunnels() -> None:
    """Stop any tunnel that has been idle for longer than its configured window."""
    for source_name, tunnel in list(_TUNNELS.items()):
        with _lock_for(source_name):
            current = _TUNNELS.get(source_name)
            if current is not tunnel:
                continue
            if current is not None and _is_idle(current):
                _TUNNELS.pop(source_name, None)
                _stop_tunnel(current)
                logger.info("Stopped idle SSM tunnel for enclave source %s", source_name)


def stop_all_tunnels() -> None:
    """Stop every tunnel (used at interpreter exit)."""
    for source_name in list(_TUNNELS):
        stop_tunnel(source_name)


def _ensure_reaper() -> None:
    global _REAPER_STARTED
    if _REAPER_STARTED:
        return
    _REAPER_STARTED = True

    def _loop() -> None:
        while True:
            time.sleep(5)
            try:
                stop_idle_tunnels()
            except Exception:  # noqa: BLE001 - a reaper must never crash
                logger.debug("Idle tunnel reaper caught an error", exc_info=True)

    threading.Thread(target=_loop, name="enclave-ssm-reaper", daemon=True).start()


atexit.register(stop_all_tunnels)


__all__ = [
    "TunnelError",
    "ensure_tunnel",
    "stop_all_tunnels",
    "stop_idle_tunnels",
    "stop_tunnel",
]
