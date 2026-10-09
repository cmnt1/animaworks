# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Known-value ledger for the egress pipeline.

Isolated anima tools register values they have read so the ``known_values``
stage can redact them when they reappear in outgoing answers. Values are
appended to ``data_dir/enclave/ledger/known_values.jsonl`` (file 0600,
directory 0700); duplicates are not written twice.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.enclave.egress.fs import ensure_dir_0700, ensure_file_0600
from core.enclave.egress.masker.facts import normalize_known_value
from core.platform.atomic_io import append_jsonl_locked

logger = logging.getLogger(__name__)


@dataclass
class _LedgerCache:
    """One process-local snapshot of an append-only JSONL ledger."""

    mtime_ns: int
    size: int
    device: int
    inode: int
    offset: int
    pending: bytes
    recorded: set[str]


_CACHE_LOCK = threading.RLock()
_CACHE: dict[Path, _LedgerCache] = {}


def _ledger_path(data_dir: Path) -> Path:
    base = data_dir / "enclave" / "ledger"
    ensure_dir_0700(base)
    path = base / "known_values.jsonl"
    if path.exists():
        os.chmod(path, 0o600)
    else:
        ensure_file_0600(path)
    return path


def _add_recorded_line(line: bytes, recorded: set[str]) -> None:
    line = line.strip()
    if not line:
        return
    try:
        rec = json.loads(line)
    except (TypeError, ValueError, UnicodeDecodeError):
        return
    value = rec.get("value") if isinstance(rec, dict) else None
    if isinstance(value, str):
        recorded.add(normalize_known_value(value))


def _load_recorded(data_dir: Path) -> set[str]:
    """Return normalized values, reading only bytes appended since the cache."""
    path = (data_dir / "enclave" / "ledger" / "known_values.jsonl").resolve()
    with _CACHE_LOCK:
        try:
            current_stat = path.stat()
        except FileNotFoundError:
            _CACHE.pop(path, None)
            return set()

        cached = _CACHE.get(path)
        signature = (current_stat.st_mtime_ns, current_stat.st_size, current_stat.st_dev, current_stat.st_ino)
        if cached is not None and signature == (
            cached.mtime_ns,
            cached.size,
            cached.device,
            cached.inode,
        ):
            return set(cached.recorded)

        append_only = (
            cached is not None
            and cached.device == current_stat.st_dev
            and cached.inode == current_stat.st_ino
            and current_stat.st_size > cached.size
        )
        with path.open("rb") as stream:
            actual_stat = os.fstat(stream.fileno())
            if append_only and (actual_stat.st_dev, actual_stat.st_ino) == (cached.device, cached.inode):
                previous_offset = cached.offset
                stream.seek(previous_offset)
                payload = cached.pending + stream.read(max(0, actual_stat.st_size - previous_offset))
                recorded = set(cached.recorded)
            else:
                stream.seek(0)
                payload = stream.read(actual_stat.st_size)
                recorded = set()

            last_newline = payload.rfind(b"\n")
            if last_newline >= 0:
                complete = payload[:last_newline].split(b"\n")
                for line in complete:
                    _add_recorded_line(line, recorded)
                pending = payload[last_newline + 1 :]
            else:
                pending = payload

            # A valid final JSONL record need not end with a newline. Keep its
            # bytes pending so a later append can complete a partial write.
            if pending:
                _add_recorded_line(pending, recorded)

        _CACHE[path] = _LedgerCache(
            mtime_ns=actual_stat.st_mtime_ns,
            size=actual_stat.st_size,
            device=actual_stat.st_dev,
            inode=actual_stat.st_ino,
            offset=actual_stat.st_size,
            pending=pending,
            recorded=recorded,
        )
        return set(recorded)


def record_known_values(data_dir: Path, values: Iterable[str], *, source: str) -> int:
    """Append *values* to the known-value ledger and return the count written.

    Values are deduplicated both against the existing ledger and within this
    call (by normalized form per source), so the same value is never stored
    twice.
    """
    path = _ledger_path(data_dir)
    recorded = _load_recorded(data_dir)
    seen_in_call: set[str] = set()
    written = 0
    ts = datetime.now(UTC).isoformat()
    for raw in values:
        if not isinstance(raw, str) or not raw:
            continue
        norm = normalize_known_value(raw)
        if not norm:
            continue
        key = (source, norm)
        if key in seen_in_call or norm in recorded:
            seen_in_call.add(key)
            continue
        seen_in_call.add(key)
        recorded.add(norm)
        record: dict[str, Any] = {"value": raw, "source": source, "ts": ts}
        append_jsonl_locked(path, record)
        written += 1
    return written
