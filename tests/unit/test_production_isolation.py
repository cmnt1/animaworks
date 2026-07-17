# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the production-environment isolation guards.

The test suite once polluted the production runtime in two ways:
  - root-logger handlers attached to ~/.animaworks/logs/errors.log when a
    test hit setup_logging() with ANIMAWORKS_DATA_DIR unset, and
  - TestStopServer POSTing a real shutdown-supervisor request to the live
    server on 127.0.0.1:18500.

tests/conftest.py now redirects ANIMAWORKS_DATA_DIR to a session temp dir in
pytest_configure() and refuses socket connections to port 18500.  These tests
fail loudly if either guard is removed.
"""

from __future__ import annotations

import errno
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from core.paths import get_data_dir


class TestDataDirIsolation:
    def test_data_dir_env_is_set(self) -> None:
        assert os.environ.get("ANIMAWORKS_DATA_DIR"), "session guard did not set ANIMAWORKS_DATA_DIR"

    def test_data_dir_is_not_production(self) -> None:
        production = (Path.home() / ".animaworks").resolve()
        resolved = get_data_dir()
        assert resolved != production
        assert not resolved.is_relative_to(production)


class TestProductionServerPortGuard:
    def test_socket_connect_is_refused(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            with pytest.raises(ConnectionRefusedError):
                sock.connect(("127.0.0.1", 18500))

    def test_socket_connect_ex_returns_econnrefused(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            assert sock.connect_ex(("127.0.0.1", 18500)) == errno.ECONNREFUSED

    def test_urllib_cannot_reach_production_server(self) -> None:
        with pytest.raises(urllib.error.URLError):
            urllib.request.urlopen("http://127.0.0.1:18500/api/system/health", timeout=2)

    def test_other_loopback_ports_still_work(self) -> None:
        """The guard must only block 18500, not local test servers."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(2)
                client.connect(("127.0.0.1", port))
