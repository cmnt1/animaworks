# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Private storage for unmodified results read by enclave tools."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.enclave.egress.fs import ensure_dir_0700

logger = logging.getLogger(__name__)

_SAFE_TOOL_RE = re.compile(r"[^A-Za-z0-9_-]+")
_SAFE_SUFFIX_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _raw_root() -> tuple[Path, Path, bool]:
    from core.config import load_config
    from core.paths import get_data_dir

    data_dir = get_data_dir().resolve()
    configured = Path(load_config().enclave.raw_dir).expanduser()
    if configured.is_absolute():
        return configured.resolve(), data_dir, False

    root = (data_dir / configured).resolve()
    if not root.is_relative_to(data_dir):
        raise ValueError("relative raw directory must remain within the data directory")
    return root, data_dir, True


def _ensure_private_root(root: Path, data_dir: Path, *, relative: bool) -> None:
    if relative:
        current = data_dir
        for component in root.relative_to(data_dir).parts:
            current = current / component
            current.mkdir(mode=0o700, exist_ok=True)
            if not current.is_dir():
                raise NotADirectoryError
            os.chmod(current, 0o700)
        ensure_dir_0700(root)
        return

    missing: list[Path] = []
    current = root
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            raise FileNotFoundError
        current = current.parent
    if not current.is_dir():
        raise NotADirectoryError
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        os.chmod(directory, 0o700)
    ensure_dir_0700(root)


def _safe_name(value: str, pattern: re.Pattern[str], *, fallback: str) -> str:
    cleaned = pattern.sub("_", value.strip()).strip("_.-")
    return cleaned[:64] or fallback


def _write_payload(stream: Any, payload: Any) -> None:
    if isinstance(payload, str):
        stream.write(payload.encode("utf-8"))
        return
    if isinstance(payload, bytes):
        stream.write(payload)
        return
    if isinstance(payload, (bytearray, memoryview)):
        stream.write(bytes(payload))
        return

    reader = getattr(payload, "read", None)
    if callable(reader):
        while True:
            chunk = reader(64 * 1024)
            if not chunk:
                break
            if isinstance(chunk, str):
                stream.write(chunk.encode("utf-8"))
            elif isinstance(chunk, bytes):
                stream.write(chunk)
            else:
                raise TypeError("raw stream returned an unsupported chunk")
        return

    serialized = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    stream.write(serialized.encode("utf-8"))


def save_raw(tool: str, payload: Any, *, suffix: str = "json") -> Path:
    """Write *payload* to a private, timestamped file and return its path.

    Strings are written verbatim, byte payloads and binary streams are copied
    unchanged, and all other values are serialized as indented UTF-8 JSON.
    """
    try:
        root, data_dir, relative = _raw_root()
        _ensure_private_root(root, data_dir, relative=relative)
        now = datetime.now(UTC)
        day_dir = ensure_dir_0700(root / now.strftime("%Y%m%d"))
        safe_tool = _safe_name(tool, _SAFE_TOOL_RE, fallback="tool")
        safe_suffix = _safe_name(suffix.lstrip("."), _SAFE_SUFFIX_RE, fallback="json")
        prefix = now.strftime("%H%M%S")

        for _ in range(10):
            path = day_dir / f"{prefix}-{safe_tool}-{secrets.token_hex(4)}.{safe_suffix}"
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                continue

            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    fd = -1
                    _write_payload(stream, payload)
                return path.resolve()
            except Exception:
                if fd >= 0:
                    os.close(fd)
                path.unlink(missing_ok=True)
                raise

        raise FileExistsError("could not allocate a unique raw result name")
    except Exception as exc:
        logger.warning("Could not save enclave raw result (%s)", type(exc).__name__)
        raise


def try_save_raw(tool: str, payload: Any, *, suffix: str = "json") -> Path | None:
    """Best-effort wrapper for tools that must still return on save failures."""
    try:
        return save_raw(tool, payload, suffix=suffix)
    except Exception:
        return None


__all__ = ["save_raw", "try_save_raw"]
