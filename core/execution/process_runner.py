from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Common lifecycle management for engine child processes."""

import asyncio
import logging
import os
import signal
import subprocess
from typing import Any

logger = logging.getLogger("animaworks.execution.process_runner")


class ProcessRunner:
    """Spawn, drain stderr from, and terminate one engine child process."""

    def __init__(self, *, graceful_timeout: float = 3.0, drain_stderr: bool = True) -> None:
        self.graceful_timeout = graceful_timeout
        self._drain_stderr_enabled = drain_stderr
        self.process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[bytes] | None = None
        self._pgid: int | None = None

    async def start(self, *command: str, **kwargs: Any) -> asyncio.subprocess.Process:
        """Start a subprocess in its own process group and begin draining stderr."""
        if self.process is not None:
            raise RuntimeError("ProcessRunner instances can only start one process")
        if os.name == "posix" and "start_new_session" not in kwargs and "preexec_fn" not in kwargs:
            kwargs["start_new_session"] = True
        self.process = await asyncio.create_subprocess_exec(*command, **kwargs)
        pid = getattr(self.process, "pid", None)
        if os.name == "posix" and isinstance(pid, int):
            try:
                pgid = os.getpgid(pid)
                if pgid not in (os.getpgrp(), 0, 1):
                    self._pgid = pgid
            except (ProcessLookupError, PermissionError, OSError):
                logger.debug("Could not resolve child process group", exc_info=True)
        if self._drain_stderr_enabled and self.process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._read_stderr(self.process.stderr))
        return self.process

    @staticmethod
    async def _read_stderr(stream: asyncio.StreamReader) -> bytes:
        """Consume stderr concurrently to prevent a full pipe stalling the child."""
        return await stream.read()

    async def stderr(self) -> bytes:
        """Return all stderr captured while the child was running."""
        if self._stderr_task is None:
            if self.process is None or self.process.stderr is None:
                return b""
            return await self.process.stderr.read()
        return await self._stderr_task

    async def terminate(self) -> None:
        """Stop the process group with TERM, a grace period, then KILL."""
        process = self.process
        if process is None:
            return
        await self.terminate_process(process, timeout=self.graceful_timeout, pgid=self._pgid)

    @staticmethod
    async def terminate_process(
        process: asyncio.subprocess.Process,
        *,
        timeout: float = 3.0,
        pgid: int | None = None,
    ) -> None:
        """Terminate a subprocess and descendants, escalating TERM to KILL."""
        pid = getattr(process, "pid", None)
        if os.name == "posix" and pgid is None and isinstance(pid, int):
            try:
                candidate = os.getpgid(pid)
                if candidate not in (os.getpgrp(), 0, 1):
                    pgid = candidate
            except (ProcessLookupError, PermissionError, TypeError, OSError):
                pgid = None

        if process.returncode is None:
            try:
                if os.name == "posix":
                    if pgid is not None:
                        os.killpg(pgid, signal.SIGTERM)
                    else:
                        process.send_signal(signal.SIGTERM)
                else:
                    process.terminate()
            except (ProcessLookupError, PermissionError, OSError):
                pass

            try:
                await asyncio.wait_for(process.wait(), timeout=max(0.001, timeout))
            except TimeoutError:
                try:
                    if os.name == "posix" and pgid is not None:
                        os.killpg(pgid, signal.SIGKILL)
                    else:
                        process.kill()
                except (ProcessLookupError, PermissionError, OSError):
                    pass
                try:
                    await process.wait()
                except Exception:
                    logger.debug("Failed waiting for killed subprocess", exc_info=True)

        # A CLI may exit while leaving tool shells behind. The process group is
        # private to this child and must not outlive the owning engine turn.
        if os.name == "posix" and pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    @staticmethod
    def terminate_popen_sync(process: Any, *, timeout: float = 3.0) -> None:
        """Terminate a synchronous SDK-owned subprocess with TERM then KILL."""
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=max(0.0, timeout))
                except (TimeoutError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait(timeout=1.0)
        except Exception:
            logger.debug("Could not terminate SDK subprocess", exc_info=True)

    @staticmethod
    def terminate_process_tree_sync(pid: int, *, timeout: float = 3.0) -> None:
        """Terminate an SDK-owned PID and descendants with TERM then KILL."""
        import psutil

        try:
            root = psutil.Process(pid)
            processes = [*root.children(recursive=True), root]
        except psutil.NoSuchProcess:
            return
        except Exception:
            logger.debug("Could not enumerate process tree for PID %s", pid, exc_info=True)
            return

        for process in processes:
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
            except Exception:
                logger.debug("Could not terminate process PID %s", process.pid, exc_info=True)
        try:
            _, alive = psutil.wait_procs(processes, timeout=max(0.0, timeout))
        except Exception:
            logger.debug("Could not wait for terminated process tree", exc_info=True)
            alive = processes
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
            except Exception:
                logger.debug("Could not kill process PID %s", process.pid, exc_info=True)
        if alive:
            psutil.wait_procs(alive, timeout=1.0)

    async def close(self) -> None:
        """Ensure the child is stopped and its stderr reader has completed."""
        await self.terminate()
        if self._stderr_task is not None and not self._stderr_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._stderr_task), timeout=1.0)
            except TimeoutError:
                self._stderr_task.cancel()
                await asyncio.gather(self._stderr_task, return_exceptions=True)

    async def __aenter__(self) -> ProcessRunner:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()
