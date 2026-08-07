"""Root-side lifecycle manager for disposable task runner processes."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.platform.process import subprocess_session_kwargs
from core.schemas import CronTask
from core.supervisor.ipc_v2 import (
    IPC_V2_MAX_FRAME_BYTES,
    IPCV2Connection,
    IPCV2ConnectionError,
    IPCV2ConnectionState,
    IPCV2Identity,
    IPCV2ProtocolError,
    ipc_v2_error,
    read_ipc_v2_envelope,
)
from core.supervisor.transport import cleanup_ipc_endpoint, start_ipc_server

logger = logging.getLogger(__name__)

_TASK_RUNNER_CONNECT_TIMEOUT = 10.0
_TASK_RUNNER_EXIT_TIMEOUT = 5.0


class TaskRunnerError(RuntimeError):
    """A task runner could not complete its execution contract."""


@dataclass
class TaskRunnerJob:
    """Root registry entry created before a task runner is spawned."""

    identity: IPCV2Identity
    request_id: str
    params: dict[str, Any]
    result: asyncio.Future[dict[str, Any]]
    peer_state: IPCV2ConnectionState
    process: asyncio.subprocess.Process | None = None
    pid: int | None = None
    pgid: int | None = None
    connection: IPCV2Connection | None = None
    last_progress: dict[str, Any] = field(default_factory=dict)


class TaskRunnerSupervisor:
    """Expose one IPC v2 endpoint and run jobs in isolated process groups."""

    def __init__(self, anima_name: str, anima_dir: Path, shared_dir: Path) -> None:
        self.anima_name = anima_name
        self.anima_dir = anima_dir
        self.shared_dir = shared_dir
        self.root_epoch = str(uuid.uuid4())
        self.socket_path = shared_dir.parent / "run" / "sockets" / f"{anima_name}.task-v2.sock"
        self._server: asyncio.Server | None = None
        self._start_lock = asyncio.Lock()
        self._jobs: dict[str, TaskRunnerJob] = {}
        self._accepting = True

    @property
    def jobs(self) -> dict[str, TaskRunnerJob]:
        """Return the live registry for health diagnostics and tests."""
        return self._jobs

    async def _ensure_started(self) -> None:
        if self._server is not None:
            return
        async with self._start_lock:
            if self._server is None:
                self._server, endpoint = await start_ipc_server(
                    self.socket_path,
                    self._handle_connection,
                    limit=IPC_V2_MAX_FRAME_BYTES + 1,
                )
                logger.info("Task runner IPC v2 endpoint started on %s", endpoint.describe())

    @staticmethod
    def _required_url_environment() -> dict[str, str]:
        """Copy model-service URLs explicitly, failing closed when absent."""
        values = {
            name: value.strip()
            for name, value in os.environ.items()
            if name.startswith("ANIMAWORKS_") and name.endswith("_URL") and value.strip()
        }
        if "ANIMAWORKS_EMBED_URL" not in values:
            raise TaskRunnerError("required task runner URL is missing: ANIMAWORKS_EMBED_URL")
        return values

    async def run_cron(self, task: CronTask) -> dict[str, Any]:
        """Spawn one cron task runner and return its terminal result."""
        return await self._run_isolated_job(
            lane="cron",
            job_prefix="cron",
            params_builder=lambda url_env: {
                "task": task.model_dump(mode="json"),
                "environment": {"urls": url_env},
            },
            log_context=f"task={task.name}",
        )

    async def run_heartbeat(
        self,
        *,
        cascade_suppressed_senders: list[str] | None = None,
    ) -> dict[str, Any]:
        """Spawn one heartbeat task runner and return its terminal result."""
        senders = list(cascade_suppressed_senders) if cascade_suppressed_senders else None
        return await self._run_isolated_job(
            lane="heartbeat",
            job_prefix="heartbeat",
            params_builder=lambda url_env: {
                "cascade_suppressed_senders": senders,
                "environment": {"urls": url_env},
            },
            log_context="heartbeat",
        )

    async def _run_isolated_job(
        self,
        *,
        lane: str,
        job_prefix: str,
        params_builder: Callable[[dict[str, str]], dict[str, Any]],
        log_context: str,
    ) -> dict[str, Any]:
        """Spawn one task runner process and return its terminal result."""
        if not self._accepting:
            raise TaskRunnerError("task runner supervisor is shutting down")
        await self._ensure_started()
        url_env = self._required_url_environment()

        job_id = f"{job_prefix}-{uuid.uuid4()}"
        request_id = f"run-{uuid.uuid4()}"
        identity = IPCV2Identity(
            job_id=job_id,
            root_epoch=self.root_epoch,
            attempt=1,
            lane=lane,
            display_lane="background",
        )
        loop = asyncio.get_running_loop()
        job = TaskRunnerJob(
            identity=identity,
            request_id=request_id,
            params=params_builder(url_env),
            result=loop.create_future(),
            peer_state=IPCV2ConnectionState(identity),
        )
        self._jobs[job_id] = job

        env = os.environ.copy()
        for name in tuple(env):
            if name.startswith("ANIMAWORKS_") and name.endswith("_URL"):
                env.pop(name)
        env.update(url_env)
        env.update(
            {
                "ANIMAWORKS_DATA_DIR": str(self.shared_dir.parent),
                "ANIMAWORKS_TASK_IPC_PATH": str(self.socket_path),
                "ANIMAWORKS_TASK_ROOT_EPOCH": self.root_epoch,
                "ANIMAWORKS_TASK_ATTEMPT": "1",
                "ANIMAWORKS_TASK_DISPLAY_LANE": "background",
                "ANIMAWORKS_TASK_ROOT_PID": str(os.getpid()),
            }
        )

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "core.supervisor.task_runner",
                "--anima",
                self.anima_name,
                "--lane",
                lane,
                "--job",
                job_id,
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                **subprocess_session_kwargs(),
            )
            job.process = process
            job.pid = process.pid
            job.pgid = process.pid
            logger.info(
                "Spawned %s task runner anima=%s %s job=%s pid=%s pgid=%s",
                lane,
                self.anima_name,
                log_context,
                job_id,
                job.pid,
                job.pgid,
            )

            process_wait = asyncio.create_task(process.wait())
            done, _ = await asyncio.wait(
                {job.result, process_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if process_wait in done and not job.result.done():
                try:
                    await asyncio.wait_for(asyncio.shield(job.result), timeout=0.25)
                except TimeoutError as exc:
                    raise TaskRunnerError(
                        f"task runner exited before returning a result (exit={process.returncode})"
                    ) from exc
            terminal = await job.result
            if not process_wait.done():
                try:
                    await asyncio.wait_for(process_wait, timeout=_TASK_RUNNER_EXIT_TIMEOUT)
                except TimeoutError as exc:
                    self._terminate_job_group(job)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2.0)
                    except TimeoutError:
                        self._kill_job_group(job)
                        await process.wait()
                    raise TaskRunnerError("task runner returned a result but did not exit") from exc
            if "error" in terminal:
                error = terminal["error"]
                raise TaskRunnerError(f"{error.get('code', 'EXECUTION_ERROR')}: {error.get('message', '')}")
            if process.returncode != 0:
                raise TaskRunnerError(f"task runner exited with status {process.returncode}")
            result = terminal.get("result")
            if not isinstance(result, dict):
                raise TaskRunnerError("task runner returned a malformed result")
            return result
        except asyncio.CancelledError:
            self._terminate_job_group(job)
            if job.process is not None:
                await job.process.wait()
            raise
        finally:
            self._jobs.pop(job_id, None)

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection: IPCV2Connection | None = None
        try:
            first = await asyncio.wait_for(
                read_ipc_v2_envelope(reader),
                timeout=_TASK_RUNNER_CONNECT_TIMEOUT,
            )
            job = self._jobs.get(first.identity.job_id)
            if job is None:
                temporary = IPCV2ConnectionState(first.identity)
                connection = IPCV2Connection(reader, writer, temporary)
                await connection.send_event(
                    "protocol_error",
                    ipc_v2_error("UNKNOWN_JOB", "job is not registered", retryable=False),
                )
                return
            connection = IPCV2Connection(reader, writer, job.peer_state)
            accepted = await connection.accept_first(first)
            if accepted is None or accepted.kind != "event" or accepted.body.get("event") != "hello":
                raise IPCV2ProtocolError("the first task runner frame must be hello")
            job.connection = connection
            hello_data = accepted.body["data"]
            last_received = hello_data.get("last_received_seq", 0)
            if not isinstance(last_received, int) or isinstance(last_received, bool) or last_received < 0:
                raise IPCV2ProtocolError("hello.last_received_seq must be a non-negative integer")
            replay_through = job.peer_state.send_seq
            await connection.send_event(
                "hello_ack",
                {
                    "capabilities": {"reconnect": True, "steer": False},
                    "last_received_seq": job.peer_state.received_seq,
                    "last_acked_seq": job.peer_state.last_acked_seq,
                },
            )
            await connection.replay_after(last_received, through_seq=replay_through)
            await connection.send_request(job.request_id, "run", job.params)

            while True:
                envelope = await asyncio.wait_for(connection.receive(), timeout=15.0)
                if envelope.kind == "response":
                    if envelope.body["request_id"] != job.request_id:
                        raise IPCV2ProtocolError("response request_id does not match the run contract")
                    terminal = (
                        {"error": envelope.body["error"]}
                        if envelope.body.get("error") is not None
                        else {"result": envelope.body["result"]}
                    )
                    if not job.result.done():
                        job.result.set_result(terminal)
                    continue
                if envelope.kind == "event" and envelope.body["event"] == "progress":
                    job.last_progress = envelope.body["data"]
                    if envelope.identity.display_lane != job.identity.display_lane:
                        raise IPCV2ProtocolError("progress display_lane does not match registry")
        except (TimeoutError, IPCV2ConnectionError):
            logger.debug("Task runner IPC connection ended", exc_info=True)
        except Exception as exc:
            logger.warning("Task runner IPC protocol failure: %s", exc, exc_info=True)
            if connection is not None and connection.state.identity.job_id in self._jobs:
                job = self._jobs.get(connection.state.identity.job_id)
                if job is not None and not job.result.done():
                    job.result.set_result({"error": ipc_v2_error("PROTOCOL_ERROR", str(exc), retryable=False)})
                    self._terminate_job_group(job)
        finally:
            if connection is not None:
                job = self._jobs.get(connection.state.identity.job_id)
                if job is not None and job.connection is connection:
                    job.connection = None
                await connection.close()
            else:
                writer.close()
                await writer.wait_closed()

    async def close(self) -> None:
        """Stop accepting jobs and reap every task runner process group."""
        self._accepting = False
        for job in list(self._jobs.values()):
            if job.connection is not None:
                try:
                    await job.connection.send_event("grace", {"deadline_seconds": _TASK_RUNNER_EXIT_TIMEOUT})
                except Exception:
                    logger.debug("Could not send grace to task runner %s", job.identity.job_id, exc_info=True)

        processes = [job.process for job in self._jobs.values() if job.process is not None]
        if processes:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(process.wait() for process in processes)),
                    timeout=_TASK_RUNNER_EXIT_TIMEOUT,
                )
            except TimeoutError:
                for job in list(self._jobs.values()):
                    self._terminate_job_group(job)
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*(process.wait() for process in processes)),
                        timeout=2.0,
                    )
                except TimeoutError:
                    for job in list(self._jobs.values()):
                        self._kill_job_group(job)
                    await asyncio.gather(*(process.wait() for process in processes), return_exceptions=True)
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        cleanup_ipc_endpoint(self.socket_path)

    @staticmethod
    def _terminate_job_group(job: TaskRunnerJob) -> None:
        process = job.process
        if process is None or process.returncode is not None:
            return
        try:
            if os.name == "posix" and job.pgid:
                os.killpg(job.pgid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return

    @staticmethod
    def _kill_job_group(job: TaskRunnerJob) -> None:
        process = job.process
        if process is None or process.returncode is not None:
            return
        try:
            if os.name == "posix" and job.pgid:
                os.killpg(job.pgid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return


__all__ = ["TaskRunnerError", "TaskRunnerJob", "TaskRunnerSupervisor"]
