from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Process-wide singleflight, TTL, and backoff for shared-index checks."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SharedCheckKey = tuple[str, str, str, str]


class SharedCheckOutcome(StrEnum):
    """Result of one shared collection check or reindex attempt."""

    SUCCESS = "success"
    TRANSIENT = "transient"
    FAILED = "failed"


@dataclass
class _Entry:
    success_until: float = 0.0
    retry_at: float = 0.0
    failures: int = 0
    last_outcome: SharedCheckOutcome | None = None


_condition = threading.Condition()
_entries: dict[SharedCheckKey, _Entry] = {}
_in_flight: dict[tuple[str, str, str], SharedCheckKey] = {}
_owner_epochs: dict[str, int] = {}


def shared_store_identity(vector_store: object) -> str:
    """Return the stable store identity used in shared-check keys."""
    attributes = getattr(vector_store, "__dict__", {})
    base_url = attributes.get("_base_url") if isinstance(attributes, dict) else None
    if isinstance(base_url, str):
        return base_url.rstrip("/")
    persist_dir = attributes.get("persist_dir") if isinstance(attributes, dict) else None
    if isinstance(persist_dir, (str, Path)):
        return f"file:{Path(persist_dir)}"
    return f"instance:{id(vector_store)}"


def make_shared_check_key(
    owner: str,
    vector_store: object,
    collection: str,
    source_generation: str,
) -> SharedCheckKey:
    """Build a key containing DB owner, store identity, collection, and source generation."""
    return owner, shared_store_identity(vector_store), collection, source_generation


def run_shared_check(
    key: SharedCheckKey,
    operation: Callable[[], SharedCheckOutcome],
    *,
    ttl_seconds: float,
    backoff_initial_seconds: float,
    backoff_max_seconds: float,
) -> SharedCheckOutcome:
    """Run one check, waiting for the same collection's active flight when needed."""
    owner, store_identity, collection, _generation = key
    flight_key = owner, store_identity, collection

    while True:
        with _condition:
            now = time.monotonic()
            entry = _entries.setdefault(key, _Entry())
            if entry.success_until > now:
                return SharedCheckOutcome.SUCCESS
            if entry.retry_at > now:
                return SharedCheckOutcome.TRANSIENT
            active_key = _in_flight.get(flight_key)
            if active_key is not None:
                while flight_key in _in_flight:
                    _condition.wait()
                completed = _entries.get(key)
                if active_key == key and completed is not None and completed.last_outcome is not None:
                    return completed.last_outcome
                continue
            entry.last_outcome = None
            _in_flight[flight_key] = key
            owner_epoch = _owner_epochs.get(owner, 0)
            break

    try:
        outcome = operation()
    except BaseException:
        with _condition:
            if _owner_epochs.get(owner, 0) == owner_epoch:
                _entries.setdefault(key, _Entry()).last_outcome = SharedCheckOutcome.FAILED
            _in_flight.pop(flight_key, None)
            _condition.notify_all()
        raise

    with _condition:
        if _owner_epochs.get(owner, 0) == owner_epoch:
            entry = _entries.setdefault(key, _Entry())
            now = time.monotonic()
            entry.last_outcome = outcome
            if outcome is SharedCheckOutcome.SUCCESS:
                entry.success_until = now + max(0.0, ttl_seconds)
                entry.retry_at = 0.0
                entry.failures = 0
            elif outcome is SharedCheckOutcome.TRANSIENT:
                entry.failures += 1
                delay = backoff_initial_seconds * (2 ** (entry.failures - 1))
                entry.retry_at = now + min(max(0.0, delay), max(0.0, backoff_max_seconds))
                entry.success_until = 0.0
        _in_flight.pop(flight_key, None)
        _condition.notify_all()
    return outcome


def invalidate_shared_checks(owner: str) -> None:
    """Invalidate all cached shared checks for one real DB owner."""
    with _condition:
        _owner_epochs[owner] = _owner_epochs.get(owner, 0) + 1
        for key in [key for key in _entries if key[0] == owner]:
            _entries.pop(key, None)
        _condition.notify_all()


def reset_shared_check_registry() -> None:
    """Reset process-wide state between tests."""
    with _condition:
        _entries.clear()
        _in_flight.clear()
        _owner_epochs.clear()
        _condition.notify_all()
