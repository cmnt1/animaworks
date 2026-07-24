from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Lease sidecars for claimed pending-task descriptors."""

import json
import os
import time
from pathlib import Path

from core.platform.process import is_process_alive


def processing_lease_path(descriptor_path: Path) -> Path:
    """Return the lease sidecar path for a processing descriptor."""
    return descriptor_path.with_name(f"{descriptor_path.name}.lease")


def write_processing_lease(
    descriptor_path: Path,
    *,
    anima: str,
    task_id: str,
    pid: int | None = None,
    leased_at: float | None = None,
) -> Path:
    """Write and return the lease sidecar for a claimed descriptor."""
    lease_path = processing_lease_path(descriptor_path)
    payload = {
        "pid": os.getpid() if pid is None else pid,
        "anima": anima,
        "leased_at": time.time() if leased_at is None else leased_at,
        "task_id": task_id,
    }
    lease_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return lease_path


def _read_proc_cmdline(pid: int) -> str:
    raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
    return raw.replace(b"\0", b" ").decode(errors="replace")


def is_processing_lease_live(
    descriptor_path: Path,
    *,
    expected_anima: str | None = None,
) -> bool:
    """Return whether a descriptor's lease belongs to its live Anima runner.

    Missing, malformed, dead, and PID-reused leases return ``False``.  If the
    platform does not expose ``/proc`` or cmdline cannot be read, a process that
    passed ``kill(pid, 0)`` is conservatively treated as live.
    """
    lease_path = processing_lease_path(descriptor_path)
    try:
        payload = json.loads(lease_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False

    pid = payload.get("pid")
    anima = payload.get("anima")
    leased_at = payload.get("leased_at")
    task_id = payload.get("task_id")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if not isinstance(anima, str) or not anima:
        return False
    if not isinstance(leased_at, (int, float)) or isinstance(leased_at, bool):
        return False
    if not isinstance(task_id, str) or not task_id:
        return False
    if expected_anima is not None and anima != expected_anima:
        return False

    if not is_process_alive(pid):
        return False

    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return True
    try:
        cmdline = _read_proc_cmdline(pid)
    except OSError:
        return True
    return "core.supervisor.runner" in cmdline and anima in cmdline
