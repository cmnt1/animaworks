"""Tests for shared crash-safe atomic I/O helpers."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.platform import atomic_io


def test_atomic_write_text_and_json_preserve_requested_content(tmp_path: Path) -> None:
    text_path = tmp_path / "nested" / "notes.txt"
    atomic_io.atomic_write_text(text_path, "hello\n")
    assert text_path.read_text(encoding="utf-8") == "hello\n"

    json_path = tmp_path / "record.json"
    payload = {"日本語": "value", "nested": {"count": 2}}
    atomic_io.atomic_write_json(json_path, payload)
    assert json_path.read_text(encoding="utf-8") == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def test_atomic_write_bytes_writes_bytes(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    atomic_io.atomic_write_bytes(path, b"\x00\xff")
    assert path.read_bytes() == b"\x00\xff"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode bits are unavailable on Windows")
def test_atomic_write_json_applies_mode(tmp_path: Path) -> None:
    path = tmp_path / "secret.json"
    atomic_io.atomic_write_json(path, {"secret": "value"}, mode=0o600)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_atomic_write_cleans_temp_and_preserves_target_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("original", encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(atomic_io.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_io.atomic_write_text(path, "replacement")

    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []


def test_atomic_write_fsyncs_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fsync = Mock()
    monkeypatch.setattr(atomic_io.os, "fsync", fsync)

    atomic_io.atomic_write_text(tmp_path / "state.txt", "durable")

    fsync.assert_called_once()


def test_memory_atomic_write_json_wraps_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.exceptions import MemoryWriteError
    from core.memory import _io

    def fail_write(*args, **kwargs):  # noqa: ANN002, ANN003
        raise OSError("disk full")

    monkeypatch.setattr(_io, "_platform_atomic_write_json", fail_write)
    with pytest.raises(MemoryWriteError, match="disk full"):
        _io.atomic_write_json(tmp_path / "memory.json", {"value": 1})
