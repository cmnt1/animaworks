"""Unit tests for core.platform.process."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psutil

from core.platform import process


class TestSubprocessSessionKwargs:
    def test_windows_returns_creationflags(self):
        with (
            patch("core.platform.process.os.name", "nt"),
            patch("core.platform.process.subprocess.CREATE_NEW_PROCESS_GROUP", 512, create=True),
        ):
            assert process.subprocess_session_kwargs() == {"creationflags": 512}

    def test_posix_returns_start_new_session(self):
        with patch("core.platform.process.os.name", "posix"):
            assert process.subprocess_session_kwargs() == {"start_new_session": True}


class TestTerminatePid:
    def test_windows_terminate_pid_kills_children_without_killpg(self):
        child = MagicMock()
        proc_obj = MagicMock()
        proc_obj.children.return_value = [child]

        with (
            patch("core.platform.process.os.name", "nt"),
            patch("core.platform.process.psutil.Process", return_value=proc_obj),
            patch("core.platform.process._terminate_psutil_process") as mock_terminate,
        ):
            process.terminate_pid(12345, force=True, include_children=True)

        assert mock_terminate.call_args_list[0].args == (child,)
        assert mock_terminate.call_args_list[0].kwargs == {"force": True}
        assert mock_terminate.call_args_list[1].args == (proc_obj,)
        assert mock_terminate.call_args_list[1].kwargs == {"force": True}

    def test_missing_pid_is_ignored(self):
        with patch(
            "core.platform.process.psutil.Process",
            side_effect=psutil.NoSuchProcess(pid=99999),
        ):
            process.terminate_pid(99999)


class TestFindMatchingPids:
    def test_filters_by_marker_user_and_python(self):
        current_proc = MagicMock()
        current_proc.username.return_value = "me"

        matching = MagicMock()
        matching.info = {
            "pid": 101,
            "cmdline": ["python", "-m", "cli", "start"],
            "exe": r"C:\Python312\python.exe",
            "name": "python.exe",
            "username": "me",
        }
        wrong_user = MagicMock()
        wrong_user.info = {
            "pid": 202,
            "cmdline": ["python", "-m", "cli", "start"],
            "exe": r"C:\Python312\python.exe",
            "name": "python.exe",
            "username": "other",
        }
        wrong_exe = MagicMock()
        wrong_exe.info = {
            "pid": 303,
            "cmdline": ["node", "main.py", "start"],
            "exe": r"C:\node.exe",
            "name": "node.exe",
            "username": "me",
        }

        with (
            patch("core.platform.process.psutil.Process", return_value=current_proc),
            patch("core.platform.process.psutil.process_iter", return_value=[matching, wrong_user, wrong_exe]),
        ):
            matches = process.find_matching_pids(("main.py start", "cli start"))

        assert matches == [101]

    def test_terminate_matching_processes_returns_count(self):
        with (
            patch("core.platform.process.find_matching_pids", return_value=[1, 2, 3]),
            patch("core.platform.process.terminate_pid") as mock_terminate,
        ):
            count = process.terminate_matching_processes(("runner",), force=True)

        assert count == 3
        assert mock_terminate.call_count == 3
