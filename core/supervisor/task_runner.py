"""Disposable task runner entry point.

Usage: ``python -m core.supervisor.task_runner --anima X --lane cron --job ID``
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from core.anima import DigitalAnima
from core.i18n import t
from core.paths import get_animas_dir, get_data_dir, get_shared_dir
from core.schemas import CronTask
from core.supervisor.ipc_v2 import (
    IPC_V2_MAX_FRAME_BYTES,
    IPCV2Connection,
    IPCV2ConnectionError,
    IPCV2ConnectionState,
    IPCV2Envelope,
    IPCV2Identity,
    IPCV2PayloadTooLarge,
    ipc_v2_error,
)
from core.supervisor.transport import open_ipc_connection

logger = logging.getLogger(__name__)

_CONNECT_DEADLINE_SECONDS = 10.0
_PROGRESS_INTERVAL_SECONDS = 5.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one isolated Anima task")
    parser.add_argument("--anima", required=True)
    parser.add_argument("--lane", required=True, choices=("chat", "heartbeat", "cron", "task", "background"))
    parser.add_argument("--job", required=True)
    return parser.parse_args(argv)


def _required_environment(args: argparse.Namespace) -> tuple[Path, IPCV2Identity]:
    embed_url = os.environ.get("ANIMAWORKS_EMBED_URL", "").strip()
    if not embed_url:
        raise RuntimeError("ANIMAWORKS_EMBED_URL is required in a task runner")
    socket_value = os.environ.get("ANIMAWORKS_TASK_IPC_PATH", "").strip()
    root_epoch = os.environ.get("ANIMAWORKS_TASK_ROOT_EPOCH", "").strip()
    attempt_value = os.environ.get("ANIMAWORKS_TASK_ATTEMPT", "").strip()
    display_lane = os.environ.get("ANIMAWORKS_TASK_DISPLAY_LANE", "").strip()
    if not socket_value or not root_epoch or not attempt_value or not display_lane:
        raise RuntimeError("task runner IPC environment is incomplete")
    identity = IPCV2Identity(
        job_id=args.job,
        root_epoch=root_epoch,
        attempt=int(attempt_value),
        lane=args.lane,
        display_lane=display_lane,
    )
    identity.validate()
    return Path(socket_value), identity


async def execute_cron_contract(anima: DigitalAnima, task: CronTask) -> dict[str, Any]:
    """Execute the complete legacy cron contract inside the child process."""
    if task.type == "llm":
        result = await anima.run_cron_task(
            task.name,
            task.description,
            **({"skills": task.skills} if task.skills else {}),
        )
        result_dict = result.model_dump(mode="json")
        return {
            "task_type": "llm",
            "result": result_dict,
            "success": result.action not in {"error", "cancelled", "failed"},
            "usage": result.usage,
        }
    if task.type != "command":
        raise ValueError(f"unknown cron type: {task.type!r}")

    result = await anima.run_cron_command(
        task.name,
        command=task.command,
        tool=task.tool,
        args=task.args,
    )
    success = result.get("exit_code", 1) == 0
    usage: dict[str, int] | None = None
    stdout = str(result.get("stdout", "")).strip()
    should_follow_up = bool(stdout and success and task.trigger_heartbeat)
    if should_follow_up and task.skip_pattern:
        try:
            should_follow_up = re.search(task.skip_pattern, stdout) is None
        except re.error as exc:
            logger.warning(
                "Invalid skip_pattern %r for task %r: %s; continuing without skip",
                task.skip_pattern,
                task.name,
                exc,
            )
    followup: dict[str, Any] | None = None
    if should_follow_up:
        followup_result = await anima.run_cron_task(
            task.name,
            task.description or t("scheduler.cron_fallback_description", task_name=task.name),
            command_output=stdout,
            **({"skills": task.skills} if task.skills else {}),
        )
        followup = followup_result.model_dump(mode="json")
        success = success and followup_result.action not in {"error", "cancelled", "failed"}
        usage = followup_result.usage
    return {
        "task_type": "command",
        "result": result,
        "followup_result": followup,
        "success": success,
        "usage": usage,
    }


async def _connect(
    socket_path: Path,
    state: IPCV2ConnectionState,
) -> tuple[IPCV2Connection, IPCV2Envelope]:
    deadline = asyncio.get_running_loop().time() + _CONNECT_DEADLINE_SECONDS
    last_error: Exception | None = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            reader, writer = await open_ipc_connection(
                socket_path,
                limit=IPC_V2_MAX_FRAME_BYTES + 1,
            )
            connection = IPCV2Connection(reader, writer, state)
            await connection.send_event(
                "hello",
                {
                    "capabilities": {"reconnect": True, "steer": False},
                    "last_received_seq": state.received_seq,
                    "last_acked_seq": state.last_acked_seq,
                },
            )
            while True:
                envelope = await connection.receive()
                if envelope.kind == "event" and envelope.body["event"] == "hello_ack":
                    continue
                if envelope.kind == "request" and envelope.body["method"] == "run":
                    return connection, envelope
        except (OSError, IPCV2ConnectionError) as exc:
            last_error = exc
            await asyncio.sleep(0.1)
    raise IPCV2ConnectionError(f"could not connect to anima root: {last_error}")


async def _progress_loop(connection: IPCV2Connection, identity: IPCV2Identity) -> None:
    while True:
        await connection.send_event(
            "progress",
            {
                "pid": os.getpid(),
                "pgid": os.getpgrp() if hasattr(os, "getpgrp") else os.getpid(),
                "lane": identity.lane,
                "job_id": identity.job_id,
                "display_lane": identity.display_lane,
                "progress_at": asyncio.get_running_loop().time(),
            },
        )
        await asyncio.sleep(_PROGRESS_INTERVAL_SECONDS)


async def _parent_monitor(expected_parent_pid: int) -> None:
    """Return when the spawning anima root is no longer our parent."""
    while os.getppid() == expected_parent_pid:
        await asyncio.sleep(1.0)


async def _send_terminal(
    connection: IPCV2Connection,
    socket_path: Path,
    state: IPCV2ConnectionState,
    request_id: str,
    *,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> IPCV2Connection:
    """Send a terminal response, reconnecting once if the socket was lost."""
    try:
        await connection.send_response(request_id, result=result, error=error)
        return connection
    except IPCV2PayloadTooLarge:
        await connection.send_response(
            request_id,
            error=ipc_v2_error(
                "PAYLOAD_TOO_LARGE",
                "task result exceeded the 4 MiB IPC frame limit",
                retryable=False,
            ),
        )
        return connection
    except IPCV2ConnectionError:
        await connection.close()
        reconnected, replayed_run = await _connect(socket_path, state)
        if replayed_run.body["request_id"] != request_id:
            await reconnected.close()
            raise
        await reconnected.send_response(request_id, result=result, error=error)
        return reconnected


async def run_task(args: argparse.Namespace, socket_path: Path, identity: IPCV2Identity) -> int:
    state = IPCV2ConnectionState(identity)
    connection, run_envelope = await _connect(socket_path, state)
    request_id = run_envelope.body["request_id"]
    params = run_envelope.body["params"]
    task_data = params.get("task")
    contract_urls = (params.get("environment") or {}).get("urls")
    if not isinstance(contract_urls, dict) or contract_urls.get("ANIMAWORKS_EMBED_URL") != os.environ.get(
        "ANIMAWORKS_EMBED_URL"
    ):
        await connection.send_response(
            request_id,
            error=ipc_v2_error(
                "PROTOCOL_ERROR",
                "run contract URL environment is missing or inconsistent",
                retryable=False,
            ),
        )
        await connection.close()
        return 2
    if not isinstance(task_data, dict):
        await connection.send_response(
            request_id,
            error=ipc_v2_error("PROTOCOL_ERROR", "run contract requires task", retryable=False),
        )
        await connection.close()
        return 2

    try:
        anima = DigitalAnima(
            anima_dir=get_animas_dir() / args.anima,
            shared_dir=get_shared_dir(),
            busy_status_enabled=False,
        )
        task = CronTask.model_validate(task_data)
    except Exception as exc:
        await connection.send_response(
            request_id,
            error=ipc_v2_error("EXECUTION_ERROR", str(exc), retryable=False),
        )
        await connection.close()
        return 1
    execution = asyncio.create_task(execute_cron_contract(anima, task))
    progress = asyncio.create_task(_progress_loop(connection, identity))
    expected_parent_pid = int(os.environ.get("ANIMAWORKS_TASK_ROOT_PID", os.getppid()))
    parent_monitor = asyncio.create_task(_parent_monitor(expected_parent_pid))
    receiver: asyncio.Task[IPCV2Envelope] | None = asyncio.create_task(
        asyncio.wait_for(connection.receive(), timeout=15.0)
    )
    cancelled = False
    root_lost = False
    try:
        while not execution.done():
            waiters: set[asyncio.Task[Any]] = {execution, parent_monitor}
            if receiver is not None:
                waiters.add(receiver)
            done, _ = await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
            if execution in done:
                break
            if parent_monitor in done:
                execution.cancel()
                root_lost = True
                break
            if receiver is not None and receiver in done:
                try:
                    control = receiver.result()
                except (IPCV2ConnectionError, TimeoutError):
                    receiver = None
                    progress.cancel()
                    continue
                if control.kind == "event" and control.body["event"] in {"cancel", "grace"}:
                    execution.cancel()
                    cancelled = True
                    break
                receiver = asyncio.create_task(asyncio.wait_for(connection.receive(), timeout=15.0))

        if cancelled or root_lost:
            try:
                await execution
            except asyncio.CancelledError:
                pass
            if not root_lost:
                connection = await _send_terminal(
                    connection,
                    socket_path,
                    state,
                    request_id,
                    error=ipc_v2_error("CANCELLED", "task runner was cancelled", retryable=True),
                )
            return 1

        try:
            result = await execution
        except Exception as exc:
            logger.exception("Task runner execution failed")
            connection = await _send_terminal(
                connection,
                socket_path,
                state,
                request_id,
                error=ipc_v2_error("EXECUTION_ERROR", str(exc), retryable=False),
            )
            return 1
        connection = await _send_terminal(
            connection,
            socket_path,
            state,
            request_id,
            result=result,
        )
        return 0
    finally:
        progress.cancel()
        parent_monitor.cancel()
        if receiver is not None:
            receiver.cancel()
        await asyncio.gather(
            progress,
            parent_monitor,
            *(tuple([receiver]) if receiver is not None else ()),
            return_exceptions=True,
        )
        await connection.close()


def _setup_logging(anima_name: str) -> None:
    from core.config import load_config
    from core.logging_config import setup_anima_logging

    try:
        redaction_enabled = load_config().logging.redaction_enabled
    except Exception:
        redaction_enabled = True
    setup_anima_logging(
        anima_name=anima_name,
        log_dir=get_data_dir() / "logs",
        level="INFO",
        also_to_console=False,
        redaction_enabled=redaction_enabled,
    )


async def main() -> int:
    args = parse_args()
    socket_path, identity = _required_environment(args)
    _setup_logging(args.anima)
    try:
        from core.config.global_permissions import GlobalPermissionsCache
        from core.paths import get_global_permissions_path

        GlobalPermissionsCache.get().load(get_global_permissions_path(), interactive=False)
    except FileNotFoundError:
        logger.warning("permissions.global.json not found; global command checks disabled")
    return await run_task(args, socket_path, identity)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"task runner startup failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
