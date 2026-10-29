# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for private enclave raw-result storage."""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.enclave.raw_store import save_raw, try_save_raw


def test_save_raw_creates_private_timestamped_json(data_dir: Path) -> None:
    payload = {"message": "dummy raw text", "rows": [["full value"]]}

    path = save_raw("enclave_sql_query", payload)

    assert path.is_absolute()
    assert path.parent.parent == data_dir / "raw"
    assert re.fullmatch(r"\d{8}", path.parent.name)
    assert re.fullmatch(r"\d{6}-enclave_sql_query-[0-9a-f]{8}\.json", path.name)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert (data_dir / "raw").stat().st_mode & 0o777 == 0o700


def test_save_raw_writes_strings_and_bytes_verbatim(data_dir: Path) -> None:
    text_path = save_raw("text-tool", "raw text\n", suffix="txt")
    binary_path = save_raw("binary-tool", b"\x00\x01raw", suffix="wav")

    assert text_path.read_bytes() == b"raw text\n"
    assert binary_path.read_bytes() == b"\x00\x01raw"
    assert binary_path.suffix == ".wav"


def test_save_raw_uses_configured_relative_directory(data_dir: Path) -> None:
    config_path = data_dir / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["enclave"] = {"raw_dir": "private/archive"}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    from core.config import invalidate_cache

    invalidate_cache()
    path = save_raw("records", [{"id": 1}])

    assert path.is_relative_to(data_dir / "private" / "archive")
    assert path.parent.parent == data_dir / "private" / "archive"
    assert (data_dir / "private").stat().st_mode & 0o777 == 0o700
    assert (data_dir / "private" / "archive").stat().st_mode & 0o777 == 0o700


def test_try_save_raw_does_not_propagate_or_log_exception_text(monkeypatch, caplog) -> None:
    import core.enclave.raw_store as raw_store

    def fail():
        raise PermissionError("dummy secret must not be logged")

    monkeypatch.setattr(raw_store, "_raw_root", fail)

    assert try_save_raw("tool", "dummy payload") is None
    assert "Could not save enclave raw result (PermissionError)" in caplog.text
    assert "dummy secret" not in caplog.text
    assert "dummy payload" not in caplog.text
