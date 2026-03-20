from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Cross-platform process helpers used by supervisor and CLI layers."""

import os
import signal
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import psutil


def subprocess_session_kwargs() -> dict[str, Any]:
    """Return Popen kwargs for launching an isolated subprocess session."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def is_process_alive(pid: int) -> bool:
    """Return True when ``pid`` exists and is not a zombie."""
    if pid <= 0 or not psutil.pid_exists(pid):
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _terminate_psutil_process(proc: psutil.Process, *, force: bool) -> None:
    try:
        if force:
            proc.kill()
        else:
            proc.terminate()
    except psutil.NoSuchProcess:
        return


def terminate_pid(pid: int, *, force: bool = False, include_children: bool = False) -> None:
    """Terminate ``pid`` and optionally its descendant processes."""
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    if include_children:
        for child in proc.children(recursive=True):
            _terminate_psutil_process(child, force=force)

    if os.name != "nt":
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL if force else signal.SIGTERM)
            return
        except OSError:
            pass

    _terminate_psutil_process(proc, force=force)


def terminate_subprocess(proc: subprocess.Popen[Any], *, force: bool = False, include_children: bool = True) -> None:
    """Terminate a ``subprocess.Popen`` instance."""
    terminate_pid(proc.pid, force=force, include_children=include_children)


def find_matching_pids(
    markers: Iterable[str],
    *,
    path_contains: str | None = None,
    exclude_pids: Iterable[int] = (),
    require_python: bool = True,
) -> list[int]:
    """Return running PIDs whose command line contains any marker."""
    marker_list = tuple(markers)
    excluded = set(exclude_pids)
    current_user = psutil.Process().username()
    matches: list[int] = []

    for proc in psutil.process_iter(["pid", "cmdline", "exe", "name", "username"]):
        try:
            pid = int(proc.info["pid"])
            if pid in excluded:
                continue
            if proc.info.get("username") != current_user:
                continue
            cmdline_parts = proc.info.get("cmdline") or []
            cmdline = " ".join(cmdline_parts)
            if not cmdline or not any(marker in cmdline for marker in marker_list):
                continue
            if path_contains and path_contains not in cmdline:
                continue
            if require_python:
                exe_name = Path(proc.info.get("exe") or proc.info.get("name") or "").name.lower()
                if "python" not in exe_name:
                    continue
            matches.append(pid)
        except (psutil.Error, TypeError, ValueError):
            continue
    return matches


def find_first_matching_pid(
    markers: Iterable[str],
    *,
    path_contains: str | None = None,
    exclude_pids: Iterable[int] = (),
    require_python: bool = True,
) -> int | None:
    """Return the first PID whose command line matches the given markers."""
    matches = find_matching_pids(
        markers,
        path_contains=path_contains,
        exclude_pids=exclude_pids,
        require_python=require_python,
    )
    return matches[0] if matches else None


def terminate_matching_processes(
    markers: Iterable[str],
    *,
    path_contains: str | None = None,
    exclude_pids: Iterable[int] = (),
    force: bool = False,
    include_children: bool = False,
    require_python: bool = True,
) -> int:
    """Terminate all matching processes and return the number targeted."""
    matches = find_matching_pids(
        markers,
        path_contains=path_contains,
        exclude_pids=exclude_pids,
        require_python=require_python,
    )
    for pid in matches:
        terminate_pid(pid, force=force, include_children=include_children)
    return len(matches)
