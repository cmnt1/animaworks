"""Unit tests for core.platform.locks."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
        file_obj.seek.assert_any_call(0)

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
