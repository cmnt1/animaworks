from __future__ import annotations

from pathlib import Path

from core.platform.pid import read_server_pid


def test_read_server_pid_valid(tmp_path: Path) -> None:
    (tmp_path / "server.pid").write_text("12345\n", encoding="utf-8")

    assert read_server_pid(tmp_path) == 12345


def test_read_server_pid_missing(tmp_path: Path) -> None:
    assert read_server_pid(tmp_path) is None


def test_read_server_pid_invalid(tmp_path: Path) -> None:
    (tmp_path / "server.pid").write_text("not_a_number", encoding="utf-8")

    assert read_server_pid(tmp_path) is None
