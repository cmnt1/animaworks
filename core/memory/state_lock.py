# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Process-safe locking for ``state/current_state.md`` updates."""

from __future__ import annotations

import errno
import threading
from pathlib import Path
from typing import Self

from core.platform.locks import acquire_file_lock, release_file_lock


class StateFileLock:
    """A thread-reentrant, process-wide exclusive lock for an Anima's state file.

    The lock protects framework-managed reads and writes of
    ``state/current_state.md``. Mode S Claude Code's built-in Write/Edit tools
    bypass this lock and therefore are not serialized by it.
    """

    def __init__(self, anima_dir: Path) -> None:
        self._lock_path = Path(anima_dir) / "state" / ".current_state.lock"
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._owner: int | None = None
        self._lock_file = None

    def acquire(self, blocking: bool = True) -> bool:
        """Acquire the lock, optionally returning immediately if it is held."""
        if not self._thread_lock.acquire(blocking):
            return False

        owner = threading.get_ident()
        if self._depth:
            # RLock ensures a non-owner cannot enter while depth is nonzero.
            self._depth += 1
            return True

        lock_file = None
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = self._lock_path.open("a+b")
            acquire_file_lock(lock_file, exclusive=True, blocking=blocking)
        except OSError as exc:
            if lock_file is not None:
                lock_file.close()
            self._thread_lock.release()
            if not blocking and exc.errno in {
                errno.EACCES,
                errno.EAGAIN,
                errno.EDEADLK,
                36,  # Windows ERROR_LOCK_VIOLATION
            }:
                return False
            raise
        except BaseException:
            if lock_file is not None:
                lock_file.close()
            self._thread_lock.release()
            raise

        self._owner = owner
        self._depth = 1
        self._lock_file = lock_file
        return True

    def release(self) -> None:
        """Release one acquisition level and unlock the file at depth zero."""
        if self._depth == 0 or self._owner != threading.get_ident():
            raise RuntimeError("StateFileLock release called by a non-owner")

        self._depth -= 1
        lock_file = self._lock_file if self._depth == 0 else None
        if self._depth == 0:
            self._owner = None
            self._lock_file = None

        try:
            if lock_file is not None:
                try:
                    release_file_lock(lock_file)
                finally:
                    lock_file.close()
        finally:
            self._thread_lock.release()

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
