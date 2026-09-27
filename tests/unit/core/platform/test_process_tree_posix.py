"""POSIX integration tests for stopping descendants outside a process group."""

from __future__ import annotations

import os
import signal
import subprocess
import time

import psutil
import pytest

from core.platform.process import signal_tree, snapshot_descendants, terminate_tree

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process groups and setsid")


def _wait_until_gone_or_zombie(pid: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return
        except psutil.NoSuchProcess:
            return
        time.sleep(0.05)
    pytest.fail(f"process {pid} remained alive after tree termination")


def _start_separate_session_grandchild() -> tuple[subprocess.Popen, int]:
    parent = subprocess.Popen(
        ["bash", "-c", "setsid bash -c 'echo $$; exec sleep 300' & wait"],
        start_new_session=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert parent.stdout is not None
    grandchild_pid = int(parent.stdout.readline().strip())
    assert os.getpgid(grandchild_pid) != os.getpgid(parent.pid)
    return parent, grandchild_pid


def test_signal_tree_reaches_new_session_grandchild() -> None:
    parent, grandchild_pid = _start_separate_session_grandchild()
    try:
        descendants = snapshot_descendants(parent.pid)
        signal_tree(
            parent.pid,
            signal.SIGKILL,
            pgid=os.getpgid(parent.pid),
            descendants=descendants,
        )
        parent.wait(timeout=5)
        _wait_until_gone_or_zombie(grandchild_pid)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if psutil.pid_exists(grandchild_pid):
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_terminate_tree_reaches_new_session_grandchild() -> None:
    parent, grandchild_pid = _start_separate_session_grandchild()
    try:
        descendants = snapshot_descendants(parent.pid)
        survivors = terminate_tree(
            parent.pid,
            descendants=descendants,
            grace_sec=1.0,
            include_root=True,
        )
        assert all(proc.pid not in {parent.pid, grandchild_pid} for proc in survivors)
        parent.wait(timeout=5)
        _wait_until_gone_or_zombie(grandchild_pid)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if psutil.pid_exists(grandchild_pid):
            try:
                os.kill(grandchild_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
