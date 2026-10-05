"""Unit tests for core.platform.locks."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.platform import locks


class TestAcquireFileLock:
    def test_windows_lock_uses_msvcrt(self):
        file_obj = MagicMock()
        file_obj.writable.return_value = True
        file_obj.tell.return_value = 0
        file_obj.fileno.return_value = 42

        fake_msvcrt = SimpleNamespace(
            LK_LOCK=1,
            LK_NBLCK=2,
            LK_UNLCK=0,
            locking=MagicMock(),
        )
        with (
            patch("core.platform.locks.os.name", "nt"),
            patch.object(locks, "msvcrt", fake_msvcrt, create=True),
        ):
            locks.acquire_file_lock(file_obj, exclusive=True, blocking=False)

        fake_msvcrt.locking.assert_called_once_with(42, fake_msvcrt.LK_NBLCK, 1)
        file_obj.seek.assert_any_call(locks._WINDOWS_LOCK_OFFSET)

    def test_posix_lock_uses_flock_flags(self):
        file_obj = MagicMock()
        fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_SH=1, LOCK_NB=4)
        fake_flock = MagicMock()
        fake_fcntl.flock = fake_flock

        with (
            patch("core.platform.locks.os.name", "posix"),
            patch.object(
                locks,
                "fcntl",
                fake_fcntl,
                create=True,
            ),
        ):
            locks.acquire_file_lock(file_obj, exclusive=True, blocking=False)

        fake_flock.assert_called_once_with(file_obj, fake_fcntl.LOCK_EX | fake_fcntl.LOCK_NB)


class TestReleaseFileLock:
    def test_windows_unlock_uses_msvcrt(self):
        file_obj = MagicMock()
        file_obj.fileno.return_value = 7

        fake_msvcrt = SimpleNamespace(
            LK_LOCK=1,
            LK_NBLCK=2,
            LK_UNLCK=0,
            locking=MagicMock(),
        )
        with (
            patch("core.platform.locks.os.name", "nt"),
            patch.object(locks, "msvcrt", fake_msvcrt, create=True),
        ):
            locks.release_file_lock(file_obj)

        fake_msvcrt.locking.assert_called_once_with(7, fake_msvcrt.LK_UNLCK, 1)


class TestFileLockContextManager:
    def test_releases_lock_on_context_exit(self):
        file_obj = MagicMock()

        with (
            patch("core.platform.locks.acquire_file_lock") as mock_acquire,
            patch("core.platform.locks.release_file_lock") as mock_release,
            locks.file_lock(file_obj, exclusive=False),
        ):
            pass

        mock_acquire.assert_called_once_with(file_obj, exclusive=False, blocking=True)
        mock_release.assert_called_once_with(file_obj)


class TestLockedPath:
    def test_thread_lock_serializes_same_path(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "nested" / "shared.lock"
        start = threading.Barrier(2)
        state_lock = threading.Lock()
        active = 0
        maximum_active = 0

        def worker() -> None:
            nonlocal active, maximum_active
            start.wait(timeout=2)
            with locks.locked_path(lock_path, thread_lock=True):
                with state_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.03)
                with state_lock:
                    active -= 1

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        assert all(not thread.is_alive() for thread in threads)
        assert maximum_active == 1

    def test_best_effort_continues_after_acquire_oserror(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        acquire = MagicMock(side_effect=OSError("lock unavailable"))
        monkeypatch.setattr(locks, "acquire_file_lock", acquire)

        with locks.locked_path(tmp_path / "best-effort.lock", best_effort=True) as lock_file:
            assert not lock_file.closed

        acquire.assert_called_once()

    def test_nonblocking_second_lock_raises_oserror(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "exclusive.lock"
        with locks.locked_path(lock_path), pytest.raises(OSError), locks.locked_path(lock_path, blocking=False):
            pytest.fail("nonblocking lock unexpectedly acquired")

    def test_windows_lock_preserves_empty_file(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "binary.lock"
        fake_msvcrt = SimpleNamespace(
            LK_LOCK=1,
            LK_NBLCK=2,
            LK_UNLCK=0,
            locking=MagicMock(),
        )
        with lock_path.open("w+b") as file_obj:
            with (
                patch("core.platform.locks.os.name", "nt"),
                patch.object(locks, "msvcrt", fake_msvcrt, create=True),
            ):
                locks.acquire_file_lock(file_obj, exclusive=True)
            file_obj.flush()
        assert lock_path.read_bytes() == b""
