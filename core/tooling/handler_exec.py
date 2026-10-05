from __future__ import annotations

from core.tooling._handler_protocols import _ExecutionToolsHost

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""ExecutionToolsMixin and background process runner for shell tools."""

import json as _json
import logging
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

from core.platform.process import subprocess_session_kwargs, terminate_subprocess
from core.tooling.handler_base import (
    _CMD_HEAD_BYTES,
    _CMD_TAIL_BYTES,
    _CMD_TRUNCATE_BYTES,
    _NEEDS_SHELL_RE,
    _error_result,
)

logger = logging.getLogger("animaworks.tool_handler")

_BG_CMD_TIMEOUT_DEFAULT = 1800  # 30 minutes
_FG_CMD_TIMEOUT_DEFAULT = 120
_BG_CMD_OUTPUT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_PIPE_THREAD_JOIN_TIMEOUT = 5.0
_PIPE_THREAD_REJOIN_TIMEOUT = 1.0


class CommandRunner:
    """Manage background command execution with streaming output to file.

    Output is written to ``state/cmd_output/{cmd_id}.txt`` in Cursor-style
    format: header (pid, command, started_at) → real-time stdout/stderr →
    footer (exit_code, elapsed_seconds).
    """

    _counter: ClassVar[int] = 0
    _counter_lock: ClassVar[threading.Lock] = threading.Lock()
    _active: ClassVar[dict[str, CommandRunner]] = {}

    def __init__(self, command: str, cwd: Path, timeout: int = _BG_CMD_TIMEOUT_DEFAULT) -> None:
        self.command = command
        self.cwd = cwd
        self.timeout = timeout
        self.cmd_id = ""
        self.pid: int | None = None
        self.process: subprocess.Popen | None = None
        self._output_path: Path = Path()
        self._start_time: float = 0.0

    @classmethod
    def _next_id(cls, prefix: str = "cmd") -> str:
        with cls._counter_lock:
            cls._counter += 1
            return f"{prefix}_{cls._counter}"

    def start(self, output_dir: Path) -> str:
        """Launch the command in background, return cmd_id immediately."""
        self.cmd_id = self._next_id()
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output_path = output_dir / f"{self.cmd_id}.txt"
        self._start_time = time.monotonic()

        _is_windows = sys.platform == "win32"
        use_shell = bool(_NEEDS_SHELL_RE.search(self.command)) or _is_windows
        try:
            if use_shell:
                self.process = subprocess.Popen(
                    self.command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(self.cwd),
                    # On Windows use cmd.exe (the default); on Unix use bash.
                    executable=None if _is_windows else "/bin/bash",
                    **subprocess_session_kwargs(),
                )
            else:
                # posix=True (the shlex default) treats backslashes as escape
                # characters, which destroys Windows paths like C:\\Users\\...
                argv = shlex.split(self.command, posix=not _is_windows)
                self.process = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(self.cwd),
                    **subprocess_session_kwargs(),
                )
        except Exception as exc:
            self._write_error_file(str(exc))
            raise

        self.pid = self.process.pid
        self._write_header()
        CommandRunner._active[self.cmd_id] = self

        stdout_thread = threading.Thread(
            target=self._stream_pipe,
            args=(self.process.stdout, ""),
            daemon=True,
            name=f"cmd-stdout-{self.cmd_id}",
        )
        stderr_thread = threading.Thread(
            target=self._stream_pipe,
            args=(self.process.stderr, "[stderr] "),
            daemon=True,
            name=f"cmd-stderr-{self.cmd_id}",
        )
        stdout_thread.start()
        stderr_thread.start()

        waiter = threading.Thread(
            target=self._wait_for_completion,
            args=(stdout_thread, stderr_thread),
            daemon=True,
            name=f"cmd-wait-{self.cmd_id}",
        )
        waiter.start()

        logger.info("background_cmd started cmd_id=%s pid=%s cmd=%s", self.cmd_id, self.pid, self.command[:80])
        return self.cmd_id

    def _write_header(self) -> None:
        from core.time_utils import now_local

        header = (
            f"--- {self.cmd_id} ---\n"
            f"pid: {self.pid}\n"
            f"command: {self.command}\n"
            f"started_at: {now_local().isoformat()}\n"
            f"status: running\n"
            f"---\n"
        )
        self._output_path.write_text(header, encoding="utf-8")

    def _write_footer(self, exit_code: int, elapsed: float, timed_out: bool = False) -> None:
        footer = f"\n--- FINISHED ---\nexit_code: {exit_code}\nelapsed_seconds: {round(elapsed, 1)}\n"
        if timed_out:
            footer += "timed_out: true\n"
        footer += "---\n"
        with open(self._output_path, "a", encoding="utf-8") as file:
            file.write(footer)

    def _write_error_file(self, error: str) -> None:
        from core.time_utils import now_local

        content = (
            f"--- {self.cmd_id or 'error'} ---\n"
            f"command: {self.command}\n"
            f"started_at: {now_local().isoformat()}\n"
            f"status: error\n"
            f"---\n"
            f"ERROR: {error}\n"
            f"--- FINISHED ---\n"
            f"exit_code: -1\n"
            f"elapsed_seconds: 0.0\n"
            f"---\n"
        )
        self._output_path.write_text(content, encoding="utf-8")

    def _stream_pipe(self, pipe: Any, prefix: str) -> None:
        """Read lines from a pipe and append to output file."""
        if pipe is None:
            return
        total_bytes = 0
        try:
            with open(self._output_path, "a", encoding="utf-8") as file:
                for line in pipe:
                    total_bytes += len(line.encode("utf-8", errors="replace"))
                    if total_bytes > _BG_CMD_OUTPUT_MAX_BYTES:
                        file.write(f"\n... (output truncated at {_BG_CMD_OUTPUT_MAX_BYTES // (1024 * 1024)} MB) ...\n")
                        file.flush()
                        break
                    file.write(f"{prefix}{line}")
                    file.flush()
        except (ValueError, OSError):
            pass
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    def _wait_for_completion(self, stdout_thread: threading.Thread, stderr_thread: threading.Thread) -> None:
        """Wait for process to finish, then write footer."""
        proc = self.process
        if proc is None:
            return
        timed_out = False
        try:
            proc.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_subprocess(proc, force=False)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                terminate_subprocess(proc, force=True)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass

        pipe_readers = (
            ("stdout", proc.stdout, stdout_thread),
            ("stderr", proc.stderr, stderr_thread),
        )
        for _, _, thread in pipe_readers:
            thread.join(timeout=_PIPE_THREAD_JOIN_TIMEOUT)

        # Preserve all output available during the normal drain window.  Only
        # force-close a pipe when its reader did not finish, then give the
        # reader one final chance to observe EOF before dropping the runner
        # from the active registry.
        for pipe_name, pipe, thread in pipe_readers:
            if not thread.is_alive():
                continue
            if pipe is not None:
                try:
                    pipe.close()
                except (OSError, ValueError):
                    logger.warning(
                        "background_cmd failed to close %s pipe cmd_id=%s",
                        pipe_name,
                        self.cmd_id,
                        exc_info=True,
                    )
            thread.join(timeout=_PIPE_THREAD_REJOIN_TIMEOUT)
            if thread.is_alive():
                logger.warning(
                    "background_cmd %s reader still alive after pipe close cmd_id=%s",
                    pipe_name,
                    self.cmd_id,
                )

        elapsed = time.monotonic() - self._start_time
        exit_code = proc.returncode if proc.returncode is not None else -1
        self._write_footer(exit_code, elapsed, timed_out=timed_out)
        CommandRunner._active.pop(self.cmd_id, None)
        logger.info(
            "background_cmd finished cmd_id=%s exit=%d elapsed=%.1fs timed_out=%s",
            self.cmd_id,
            exit_code,
            elapsed,
            timed_out,
        )


class ExecutionToolsMixin:
    """Run foreground or background shell commands after permission checks."""

    def _handle_execute_command(self: _ExecutionToolsHost, args: dict[str, Any]) -> str:
        context = self._tool_context
        command = args.get("command", "")
        err = context.check_command_permission(command)
        if err:
            return err

        background = args.get("background", False)
        if background:
            timeout = args.get("timeout", _BG_CMD_TIMEOUT_DEFAULT)
            runner = CommandRunner(command, context.task_cwd or context.anima_dir, timeout)
            output_dir = context.anima_dir / "state" / "cmd_output"
            try:
                cmd_id = runner.start(output_dir)
            except Exception as exc:
                return _error_result("ExecutionError", f"Failed to start background command: {exc}")
            return _json.dumps(
                {
                    "status": "background",
                    "cmd_id": cmd_id,
                    "output_file": str(runner._output_path),
                },
                ensure_ascii=False,
            )

        timeout = args.get("timeout", _FG_CMD_TIMEOUT_DEFAULT)

        import platform as _platform

        _is_windows = _platform.system() == "Windows"
        use_shell = bool(_NEEDS_SHELL_RE.search(command)) or _is_windows

        try:
            if use_shell:
                shell_kwargs: dict[str, Any] = {}
                if not _is_windows:
                    shell_kwargs["executable"] = "/bin/bash"
                proc = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(context.task_cwd or context.anima_dir),
                    **shell_kwargs,
                )
            else:
                try:
                    argv = shlex.split(command)
                except ValueError as exc:
                    return _error_result("InvalidArguments", f"Error parsing command: {exc}")
                proc = subprocess.run(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(context.task_cwd or context.anima_dir),
                )
            output = proc.stdout
            if proc.stderr:
                output += f"\n[stderr]\n{proc.stderr}"
            logger.info(
                "execute_command cmd=%s rc=%d shell=%s",
                command[:80],
                proc.returncode,
                use_shell,
            )
            if len(output.encode("utf-8", errors="replace")) > _CMD_TRUNCATE_BYTES:
                encoded = output.encode("utf-8", errors="replace")
                head = encoded[:_CMD_HEAD_BYTES].decode("utf-8", errors="ignore")
                tail = encoded[-_CMD_TAIL_BYTES:].decode("utf-8", errors="ignore")
                output = f"{head}\n\n... [truncated: {len(encoded)} bytes total] ...\n\n{tail}"
            return output or f"(exit code {proc.returncode})"
        except subprocess.TimeoutExpired:
            return _error_result(
                "Timeout",
                f"Command timed out after {timeout}s",
                suggestion="Increase timeout or use background=true for long-running commands",
            )
        except Exception as exc:
            return _error_result("ExecutionError", f"Error executing command: {exc}")
