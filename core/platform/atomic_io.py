from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Crash-safe atomic file writing helpers shared across the application."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    mode: int | None = None,
    fsync_dir: bool = False,
) -> None:
    """Atomically write bytes using a unique sibling temporary file."""
    _atomic_write_data(path, data, mode=mode, fsync_dir=fsync_dir)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
    fsync_dir: bool = False,
) -> None:
    """Atomically write text using a unique sibling temporary file."""
    _atomic_write_data(path, text, encoding=encoding, mode=mode, fsync_dir=fsync_dir)


def atomic_write_json(
    path: Path,
    obj: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    trailing_newline: bool = True,
    sort_keys: bool = False,
    mode: int | None = None,
    fsync_dir: bool = False,
) -> None:
    """Atomically serialize JSON with explicitly configurable formatting."""
    text = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys)
    if trailing_newline:
        text += "\n"
    atomic_write_text(path, text, mode=mode, fsync_dir=fsync_dir)


def _atomic_write_data(
    path: Path,
    data: bytes | str,
    *,
    encoding: str | None = None,
    mode: int | None = None,
    fsync_dir: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        if isinstance(data, bytes):
            stream = os.fdopen(fd, "wb")
        else:
            stream = os.fdopen(fd, "w", encoding=encoding)
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Failed to unlink atomic-write temp file %s", temp_path, exc_info=True)
        raise

    if fsync_dir:
        _fsync_directory(path.parent)


def _fsync_directory(directory: Path) -> None:
    """Best-effort fsync of a directory after replacing its entry."""
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:
        logger.debug("Failed to open directory for fsync: %s", directory, exc_info=True)
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        logger.debug("Failed to fsync directory %s", directory, exc_info=True)
    finally:
        try:
            os.close(dir_fd)
        except OSError:
            logger.debug("Failed to close directory after fsync: %s", directory, exc_info=True)
