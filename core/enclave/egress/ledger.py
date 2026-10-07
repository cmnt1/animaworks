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

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.enclave.egress.fs import ensure_dir_0700, ensure_file_0600
from core.enclave.egress.masker.facts import normalize_known_value
from core.platform.atomic_io import append_jsonl_locked

logger = logging.getLogger(__name__)


def _ledger_path(data_dir: Path) -> Path:
    base = data_dir / "enclave" / "ledger"
    ensure_dir_0700(base)
    path = base / "known_values.jsonl"
    ensure_file_0600(path)
    return path


def _load_recorded(data_dir: Path) -> set[str]:
    """Return the set of already-recorded normalized values."""
    path = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    recorded: set[str] = set()
    if not path.exists():
        return recorded
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                import json

                rec = json.loads(line)
            except Exception:  # tolerate a malformed line, keep going
                continue
            value = rec.get("value")
            if isinstance(value, str):
                recorded.add(normalize_known_value(value))
    return recorded


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
