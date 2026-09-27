from __future__ import annotations

import multiprocessing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.anima.heartbeat import HeartbeatMixin
from core.memory.manager import MemoryManager
from core.memory.state_lock import StateFileLock
from tests.helpers.filesystem import create_anima_dir, create_test_data_dir


def _try_nonblocking_state_lock(anima_dir: str, results) -> None:
    lock = StateFileLock(Path(anima_dir))
    acquired = lock.acquire(blocking=False)
    results.put(acquired)
    if acquired:
        lock.release()


@pytest.fixture
def anima_dir(tmp_path: Path, monkeypatch) -> Path:
    data_dir = create_test_data_dir(tmp_path)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))
    from core.config import invalidate_cache

    invalidate_cache()
    path = create_anima_dir(data_dir, "state-lock-test")
    yield path
    invalidate_cache()


def test_state_file_lock_is_reentrant_for_same_thread(anima_dir: Path) -> None:
    lock = StateFileLock(anima_dir)

    with lock:
        assert lock.acquire()
        assert lock._depth == 2
        lock.release()
        assert lock._depth == 1

    assert lock._depth == 0


def test_state_file_lock_serializes_processes(anima_dir: Path) -> None:
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    lock = StateFileLock(anima_dir)

    with lock:
        process = context.Process(target=_try_nonblocking_state_lock, args=(str(anima_dir), results))
        process.start()
        assert results.get(timeout=10) is False
        process.join(timeout=10)
        assert process.exitcode == 0

    process = context.Process(target=_try_nonblocking_state_lock, args=(str(anima_dir), results))
    process.start()
    assert results.get(timeout=10) is True
    process.join(timeout=10)
    assert process.exitcode == 0


def test_state_read_modify_write_paths_acquire_state_lock(anima_dir: Path) -> None:
    memory = MemoryManager(anima_dir)
    memory._rag.index_file = MagicMock()
    memory.update_state("x" * 200)
    owner = SimpleNamespace(
        name="state-lock-test",
        memory=memory,
        _get_current_state_max_chars=lambda: 100,
    )

    with patch.object(memory.state_lock, "acquire", wraps=memory.state_lock.acquire) as acquire:
        HeartbeatMixin._enforce_state_size_limit(owner)
    acquire.assert_called_once_with()
