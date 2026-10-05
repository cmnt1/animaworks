from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from core.memory.rag.owner_lock import VectorOwnerBusy, VectorOwnerLock, is_owner_lock_held, owner_lock_path


def test_owner_lock_acquires_and_releases(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "sora"
    lock = VectorOwnerLock(anima_dir, "root")

    lock.acquire()

    assert lock.held
    assert owner_lock_path(anima_dir).read_text(encoding="utf-8").startswith("pid=")
    assert is_owner_lock_held(anima_dir)
    lock.release()
    assert not lock.held
    assert not is_owner_lock_held(anima_dir)


def test_owner_lock_rejects_double_owner(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "sora"
    first = VectorOwnerLock(anima_dir, "root")
    second = VectorOwnerLock(anima_dir, "cli:index")
    first.acquire()
    try:
        with pytest.raises(VectorOwnerBusy):
            second.acquire()
    finally:
        first.release()


def test_owner_lock_waits_until_current_owner_releases(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "sora"
    first = VectorOwnerLock(anima_dir, "root")
    second = VectorOwnerLock(anima_dir, "cli:index")
    first.acquire()
    threading.Timer(0.1, first.release).start()

    second.acquire(wait_seconds=1.0)

    assert second.held
    second.release()
    time.sleep(0.01)
    assert not is_owner_lock_held(anima_dir)
