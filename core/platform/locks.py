from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Cross-platform advisory file locking helpers."""

import contextlib
import logging
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

if os.name == "nt":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)

_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[resolved] = lock
        return lock


def _prepare_windows_lock(file_obj: IO[Any]) -> None:
    if not file_obj.writable():
        file_obj.seek(0)
        return
    current = file_obj.tell()
    file_obj.seek(0, os.SEEK_END)
    if file_obj.tell() == 0:
        placeholder = b"\0" if "b" in getattr(file_obj, "mode", "") else "\0"
        file_obj.write(placeholder)
        file_obj.flush()
    file_obj.seek(current)


def acquire_file_lock(
    file_obj: IO[Any],
    *,
    exclusive: bool,
    blocking: bool = True,
) -> None:
    """Acquire an advisory file lock on ``file_obj``."""
    if os.name == "nt":
        _prepare_windows_lock(file_obj)
        file_obj.seek(0)
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        msvcrt.locking(file_obj.fileno(), mode, 1)
        return

    flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    if not blocking:
        flags |= fcntl.LOCK_NB
    fcntl.flock(file_obj, flags)


def release_file_lock(file_obj: IO[Any]) -> None:
    """Release a previously acquired advisory file lock."""
    if os.name == "nt":
        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(file_obj, fcntl.LOCK_UN)


@contextlib.contextmanager
def file_lock(
    file_obj: IO[Any],
    *,
    exclusive: bool,
    blocking: bool = True,
) -> Iterator[IO[Any]]:
    """Context manager wrapper around :func:`acquire_file_lock`."""
    acquire_file_lock(file_obj, exclusive=exclusive, blocking=blocking)
    try:
        yield file_obj
    finally:
        release_file_lock(file_obj)


@contextlib.contextmanager
def locked_path(
    lock_path: Path,
    *,
    exclusive: bool = True,
    blocking: bool = True,
    thread_lock: bool = False,
    best_effort: bool = False,
) -> Iterator[IO[str]]:
    """Lock a path, optionally coordinating threads and tolerating OS lock errors."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    thread_guard = _thread_lock_for(lock_path) if thread_lock else contextlib.nullcontext()
    with thread_guard, lock_path.open("a+", encoding="utf-8") as lock_file:
        acquired = False
        try:
            acquire_file_lock(lock_file, exclusive=exclusive, blocking=blocking)
            acquired = True
        except OSError:
            if not best_effort:
                raise
            logger.debug("OS file lock unavailable for %s; proceeding without lock", lock_path, exc_info=True)
        try:
            yield lock_file
        finally:
            if acquired:
                try:
                    release_file_lock(lock_file)
                except OSError:
                    if not best_effort:
                        raise
                    logger.debug("Failed to release OS file lock %s", lock_path, exc_info=True)
