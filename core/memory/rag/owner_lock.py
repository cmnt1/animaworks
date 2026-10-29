"""Exclusive ownership lock for an anima's native vector database."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import IO

from core.platform.locks import acquire_file_lock, release_file_lock


class VectorOwnerBusy(RuntimeError):
    """Raised when another process owns an anima's vector database."""


class VectorOwnerLock:
    """Hold an advisory file lock while a process owns a native vector store."""

    def __init__(self, anima_dir: Path, owner_label: str) -> None:
        self.path = owner_lock_path(anima_dir)
        self.owner_label = owner_label
        self._file: IO[str] | None = None

    @property
    def held(self) -> bool:
        return self._file is not None

    def acquire(self, *, wait_seconds: float = 0.0) -> None:
        """Acquire ownership, retrying at 500ms intervals up to the deadline."""
        if self.held:
            return
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = self.path.open("a+", encoding="utf-8")
            try:
                acquire_file_lock(lock_file, exclusive=True, blocking=False)
            except OSError as exc:
                try:
                    lock_file.seek(0)
                    holder = lock_file.read().strip()
                finally:
                    lock_file.close()
                if time.monotonic() >= deadline:
                    detail = f" (held by {holder})" if holder else ""
                    raise VectorOwnerBusy(f"Vector database owner is busy: {self.path}{detail}") from exc
                time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
                continue

            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(f"pid={os.getpid()} owner={self.owner_label}\n")
            lock_file.flush()
            self._file = lock_file
            return

    def release(self) -> None:
        """Release ownership and close the lock file."""
        lock_file, self._file = self._file, None
        if lock_file is None:
            return
        try:
            release_file_lock(lock_file)
        finally:
            lock_file.close()


def owner_lock_path(anima_dir: Path) -> Path:
    """Return the canonical lock path for an anima directory."""
    return anima_dir / "state" / "vectordb.owner.lock"


def is_owner_lock_held(anima_dir: Path) -> bool:
    """Check whether another process currently owns the anima's vector DB."""
    path = owner_lock_path(anima_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        try:
            acquire_file_lock(lock_file, exclusive=True, blocking=False)
        except OSError:
            return True
        release_file_lock(lock_file)
        return False
