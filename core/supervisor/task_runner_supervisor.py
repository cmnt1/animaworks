"""Root-side lifecycle manager for disposable task runner processes."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import signal
import sys
import uuid
from collections.abc import Awaitable, Callable
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
from core.supervisor.memory_service import MemoryService, MemoryServiceUnavailable
from core.supervisor.transport import cleanup_ipc_endpoint, start_ipc_server

logger = logging.getLogger(__name__)

_TASK_RUNNER_CONNECT_TIMEOUT = 10.0
_TASK_RUNNER_EXIT_TIMEOUT = 5.0
_TASK_RUNNER_TERM_TIMEOUT = 5.0
_HANG_CHECK_INTERVAL_MAX = 5.0

OnSpawned = Callable[["TaskRunnerJob"], Awaitable[None] | None]


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
    last_progress_at: float = 0.0
    hang_kill_started: bool = False
    grace_acked: asyncio.Event = field(default_factory=asyncio.Event)
    process_start_time: float | None = None


class TaskRunnerSupervisor:
    """Expose one IPC v2 endpoint and run jobs in isolated process groups."""

    def __init__(
        self,
        anima_name: str,
        anima_dir: Path,
        shared_dir: Path,
        *,
        max_concurrent: int | None = None,
        busy_hang_threshold_sec: float = 900.0,
        busy_status_owner: Any | None = None,
        memory_via_root: bool = False,
    ) -> None:
        self.anima_name = anima_name
        self.anima_dir = anima_dir
        self.shared_dir = shared_dir
        self.root_epoch = str(uuid.uuid4())
        self.socket_path = shared_dir.parent / "run" / "sockets" / f"{anima_name}.task-v2.sock"
        self._server: asyncio.Server | None = None
        self._memory_service = MemoryService(anima_name, anima_dir) if memory_via_root else None
        self._start_lock = asyncio.Lock()
        self._jobs: dict[str, TaskRunnerJob] = {}
        self._accepting = True
        self._busy_hang_threshold_sec = max(0.0, float(busy_hang_threshold_sec))
        self._hang_check_interval = min(
            _HANG_CHECK_INTERVAL_MAX,
            max(0.05, self._busy_hang_threshold_sec / 2),
        )
        self._busy_status_owner = busy_status_owner
        set_provider = getattr(busy_status_owner, "_set_isolated_busy_jobs_provider", None)
        if callable(set_provider):
            set_provider(lambda: self._jobs)
        # Cap concurrent child processes for task/background lanes (pool size).
        pool = max_concurrent if isinstance(max_concurrent, int) and max_concurrent >= 1 else None
        self._max_concurrent = pool
        self._spawn_semaphore = asyncio.Semaphore(pool) if pool is not None else None

    @property
    def jobs(self) -> dict[str, TaskRunnerJob]:
        """Return the live registry for health diagnostics and tests."""
        return self._jobs

    @property
    def active_child_count(self) -> int:
        """Number of currently registered task-runner jobs."""
        return len(self._jobs)

    async def _ensure_started(self) -> None:
        if self._server is not None:
            return
        async with self._start_lock:
            if self._server is None:
                if self._memory_service is not None:
                    await self._memory_service.start()
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

    async def run_task(
        self,
        task_desc: dict[str, Any],
        *,
        attempt: int = 1,
        display_lane: str = "background",
        on_spawned: OnSpawned | None = None,
    ) -> dict[str, Any]:
        """Spawn one TaskExec (lane=task) runner and return its terminal result."""
        task_id = str(task_desc.get("task_id") or "unknown")
        return await self._run_isolated_job(
            lane="task",
            job_prefix="task",
            params_builder=lambda url_env: {
                "task_desc": task_desc,
                "environment": {"urls": url_env},
            },
            log_context=f"task_id={task_id}",
            attempt=attempt,
            display_lane=display_lane,
            on_spawned=on_spawned,
            use_pool_limit=True,
        )

    async def run_background(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        attempt: int = 1,
        display_lane: str = "background",
        on_spawned: OnSpawned | None = None,
    ) -> dict[str, Any]:
        """Spawn one background-lane runner (command tool or consolidation)."""
        return await self._run_isolated_job(
            lane="background",
            job_prefix=f"bg-{kind}",
            params_builder=lambda url_env: {
                "kind": kind,
                "payload": payload,
                "environment": {"urls": url_env},
            },
            log_context=f"kind={kind}",
            attempt=attempt,
            display_lane=display_lane,
            on_spawned=on_spawned,
            use_pool_limit=True,
        )

    async def _run_isolated_job(
        self,
        *,
        lane: str,
        job_prefix: str,
        params_builder: Callable[[dict[str, str]], dict[str, Any]],
        log_context: str,
        attempt: int = 1,
        display_lane: str = "background",
        on_spawned: OnSpawned | None = None,
        use_pool_limit: bool = False,
    ) -> dict[str, Any]:
        """Spawn one task runner process and return its terminal result."""
        if not self._accepting:
            raise TaskRunnerError("task runner supervisor is shutting down")
        await self._ensure_started()
        url_env = self._required_url_environment()

        if attempt < 1:
            raise TaskRunnerError("attempt must be >= 1")

        sem = self._spawn_semaphore if use_pool_limit else None
        if sem is not None:
            await sem.acquire()
        try:
            return await self._spawn_and_await(
                lane=lane,
                job_prefix=job_prefix,
                params_builder=params_builder,
                log_context=log_context,
                attempt=attempt,
                display_lane=display_lane,
                on_spawned=on_spawned,
                url_env=url_env,
            )
        finally:
            if sem is not None:
                sem.release()

    async def _spawn_and_await(
        self,
        *,
        lane: str,
        job_prefix: str,
        params_builder: Callable[[dict[str, str]], dict[str, Any]],
        log_context: str,
        attempt: int,
        display_lane: str,
        on_spawned: OnSpawned | None,
        url_env: dict[str, str],
    ) -> dict[str, Any]:
        job_id = f"{job_prefix}-{uuid.uuid4()}"
        request_id = f"run-{uuid.uuid4()}"
        identity = IPCV2Identity(
            job_id=job_id,
            root_epoch=self.root_epoch,
            attempt=attempt,
            lane=lane,
            display_lane=display_lane,
        )
        loop = asyncio.get_running_loop()
        job = TaskRunnerJob(
            identity=identity,
            request_id=request_id,
            params=params_builder(url_env),
            result=loop.create_future(),
            peer_state=IPCV2ConnectionState(identity),
            last_progress_at=loop.time(),
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
                "ANIMAWORKS_TASK_ATTEMPT": str(attempt),
                "ANIMAWORKS_TASK_DISPLAY_LANE": display_lane,
                "ANIMAWORKS_TASK_ROOT_PID": str(os.getpid()),
            }
        )
        if self._memory_service is not None:
            env["ANIMAWORKS_MEMORY_VIA_ROOT"] = "1"

        hang_watch: asyncio.Task[None] | None = None
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
            self._mark_busy_start()
            try:
                import psutil

                job.process_start_time = float(psutil.Process(process.pid).create_time())
            except Exception:
                job.process_start_time = None
            logger.info(
                "Spawned %s task runner anima=%s %s job=%s pid=%s pgid=%s attempt=%s",
                lane,
                self.anima_name,
                log_context,
                job_id,
                job.pid,
                job.pgid,
                attempt,
            )
            if on_spawned is not None:
                maybe = on_spawned(job)
                if inspect.isawaitable(maybe):
                    await maybe

            process_wait = asyncio.create_task(process.wait())
            hang_watch = asyncio.create_task(self._watch_job(job))
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
            if hang_watch is not None:
                if not job.hang_kill_started:
                    hang_watch.cancel()
                await asyncio.gather(hang_watch, return_exceptions=True)
            self._jobs.pop(job_id, None)
            self._clear_busy_if_idle()
            # A-07: recover orphan streaming journals after every task ends.
            self._recover_task_journals()

    async def _watch_job(self, job: TaskRunnerJob) -> None:
        """Kill only this task-runner group after progress stops."""
        while job.identity.job_id in self._jobs:
            await asyncio.sleep(self._hang_check_interval)
            process = job.process
            if process is None or process.returncode is not None:
                return
            idle_sec = asyncio.get_running_loop().time() - job.last_progress_at
            if idle_sec <= self._busy_hang_threshold_sec:
                continue
            job.hang_kill_started = True
            logger.error(
                "Task runner hang: anima=%s job=%s lane=%s pid=%s pgid=%s idle=%.1fs threshold=%.1fs",
                self.anima_name,
                job.identity.job_id,
                job.identity.lane,
                job.pid,
                job.pgid,
                idle_sec,
                self._busy_hang_threshold_sec,
            )
            await self._terminate_hung_job(job)
            return

    async def _terminate_hung_job(self, job: TaskRunnerJob) -> None:
        """Terminate a hung task group, escalating to SIGKILL after grace."""
        process = job.process
        if process is None:
            return
        self._terminate_job_group(job)
        try:
            await asyncio.wait_for(asyncio.shield(process.wait()), timeout=_TASK_RUNNER_TERM_TIMEOUT)
        except TimeoutError:
            pass
        if self._job_group_exists(job):
            self._kill_job_group(job)
        if process.returncode is None:
            await process.wait()

    @staticmethod
    def _job_group_exists(job: TaskRunnerJob) -> bool:
        if os.name != "posix" or not job.pgid:
            return bool(job.process is not None and job.process.returncode is None)
        try:
            os.killpg(job.pgid, 0)
        except ProcessLookupError:
            return False
        return True

    def _mark_busy_start(self) -> None:
        owner = self._busy_status_owner
        if owner is None:
            return
        callback = getattr(owner, "_mark_busy_start" if len(self._jobs) == 1 else "_mark_busy_progress", None)
        if callable(callback):
            callback()

    def _mark_busy_progress(self) -> None:
        callback = getattr(self._busy_status_owner, "_mark_busy_progress", None)
        if callable(callback):
            callback()

    def _record_progress(self, job: TaskRunnerJob, data: dict[str, Any]) -> None:
        job.last_progress = data
        job.last_progress_at = asyncio.get_running_loop().time()
        self._mark_busy_progress()

    def _clear_busy_if_idle(self) -> None:
        callback = getattr(self._busy_status_owner, "_clear_busy_status_sidecar_if_idle", None)
        if callable(callback):
            callback()

    def _recover_task_journals(self) -> None:
        """Best-effort orphan StreamingJournal recovery after a child exits."""
        try:
            from core.memory.streaming_journal import StreamingJournal
        except Exception:
            return
        for session_type in ("task", "heartbeat", "chat", "cron"):
            try:
                if not StreamingJournal.has_orphan(self.anima_dir, session_type=session_type):
                    continue
                thread_ids = StreamingJournal.list_orphan_thread_ids(self.anima_dir, session_type)
                for thread_id in thread_ids or ("default",):
                    recovery = StreamingJournal.recover(
                        self.anima_dir,
                        session_type,
                        thread_id=thread_id,
                    )
                    if recovery is not None:
                        StreamingJournal.confirm_recovery(
                            self.anima_dir,
                            session_type,
                            thread_id=thread_id,
                        )
                        logger.info(
                            "Recovered orphan journal after task exit: anima=%s session=%s thread=%s",
                            self.anima_name,
                            session_type,
                            thread_id,
                        )
            except Exception:
                logger.debug(
                    "Orphan journal recovery failed for %s/%s",
                    self.anima_name,
                    session_type,
                    exc_info=True,
                )

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
                if envelope.kind == "request":
                    await self._handle_memory_request(connection, envelope)
                    continue
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
                    if envelope.identity.display_lane != job.identity.display_lane:
                        raise IPCV2ProtocolError("progress display_lane does not match registry")
                    self._record_progress(job, envelope.body["data"])
                    continue
                if envelope.kind == "event" and envelope.body["event"] == "grace_ack":
                    job.grace_acked.set()
                    continue
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

    async def _handle_memory_request(self, connection: IPCV2Connection, envelope: Any) -> None:
        request_id = envelope.body["request_id"]
        method = envelope.body["method"]
        params = envelope.body["params"]
        if not method.startswith("memory."):
            await connection.send_response(
                request_id,
                error=ipc_v2_error("PROTOCOL_ERROR", f"unsupported task request: {method}", retryable=False),
            )
            return
        try:
            result = await self.handle_memory(method, params)
        except MemoryServiceUnavailable as exc:
            await connection.send_response(
                request_id,
                error=ipc_v2_error(
                    "UNAVAILABLE",
                    str(exc),
                    retryable=True,
                    retry_after_ms=250,
                ),
            )
        except ValueError as exc:
            await connection.send_response(
                request_id,
                error=ipc_v2_error("PROTOCOL_ERROR", str(exc), retryable=False),
            )
        else:
            await connection.send_response(request_id, result=result)

    async def handle_memory(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Serve root-local and IPC callers through the same memory queue."""
        if self._memory_service is None:
            raise MemoryServiceUnavailable("root memory service is disabled")
        return await self._memory_service.handle(method, params)

    async def close(self) -> None:
        """Stop accepting jobs, grace active runners, then reap process groups."""
        self._accepting = False
        for job in list(self._jobs.values()):
            if job.connection is not None:
                try:
                    await job.connection.send_event(
                        "grace",
                        {"deadline_seconds": _TASK_RUNNER_EXIT_TIMEOUT},
                    )
                except Exception:
                    logger.debug(
                        "Could not send grace to task runner %s",
                        job.identity.job_id,
                        exc_info=True,
                    )

        # Wait briefly for grace_ack from each child before escalating.
        if self._jobs:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(job.grace_acked.wait() for job in self._jobs.values())),
                    timeout=_TASK_RUNNER_EXIT_TIMEOUT,
                )
            except TimeoutError:
                logger.debug("Timed out waiting for grace_ack from some task runners")

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
        if self._memory_service is not None:
            await self._memory_service.close()
        cleanup_ipc_endpoint(self.socket_path)
        self._recover_task_journals()

    @staticmethod
    def _terminate_job_group(job: TaskRunnerJob) -> None:
        process = job.process
        if process is None:
            return
        try:
            if os.name == "posix" and job.pgid:
                os.killpg(job.pgid, signal.SIGTERM)
            elif process.returncode is None:
                process.terminate()
        except ProcessLookupError:
            return

    @staticmethod
    def _kill_job_group(job: TaskRunnerJob) -> None:
        process = job.process
        if process is None:
            return
        try:
            if os.name == "posix" and job.pgid:
                os.killpg(job.pgid, signal.SIGKILL)
            elif process.returncode is None:
                process.kill()
        except ProcessLookupError:
            return


__all__ = ["TaskRunnerError", "TaskRunnerJob", "TaskRunnerSupervisor"]
