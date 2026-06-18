from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Lightweight memory telemetry for long-running Anima runner processes."""

import gc
import json
import os
from pathlib import Path
from typing import Any

import psutil

from core.time_utils import now_iso


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def sample_process_memory(
    *,
    anima_name: str,
    stage: str,
    run_dir: Path,
    pid: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one memory sample to ``run/memory/process_samples.jsonl``.

    On Windows, ``psutil.Process.memory_info().rss`` represents the process
    working set, so the JSONL uses both ``rss_bytes`` and ``working_set_bytes``
    for easier dashboard/report consumption.
    """

    if os.environ.get("ANIMAWORKS_MEMORY_PROBE", "1").strip().lower() in {"0", "false", "no", "off"}:
        return {}

    target_pid = pid or os.getpid()
    proc = psutil.Process(target_pid)
    mem = proc.memory_info()
    full_mem = None
    try:
        full_mem = proc.memory_full_info()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        full_mem = None

    children_rss = 0
    child_count = 0
    try:
        for child in proc.children(recursive=True):
            try:
                children_rss += int(child.memory_info().rss)
                child_count += 1
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    sample: dict[str, Any] = {
        "ts": now_iso(),
        "anima": anima_name,
        "stage": stage,
        "pid": target_pid,
        "rss_bytes": int(mem.rss),
        "working_set_bytes": int(mem.rss),
        "vms_bytes": int(mem.vms),
        "uss_bytes": _to_int(getattr(full_mem, "uss", None)),
        "private_bytes": _to_int(getattr(full_mem, "private", None)),
        "children_rss_bytes": children_rss,
        "child_process_count": child_count,
        "thread_count": proc.num_threads(),
        "gc_counts": list(gc.get_count()),
    }
    if extra:
        sample["extra"] = extra

    memory_dir = run_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / "process_samples.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample, ensure_ascii=False, default=str) + "\n")
    return sample
