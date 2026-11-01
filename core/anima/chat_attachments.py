from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Outbound chat attachments produced by an Anima during a reply."""

import json
import logging
import mimetypes
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Any

from core.i18n import t
from core.time_utils import now_local

logger = logging.getLogger("animaworks.chat_attachments")

MAX_CHAT_FILENAME_LENGTH = 120
MAX_OUTBOUND_FILE_SIZE = 100 * 1024 * 1024
MAX_OUTBOUND_FILE_COUNT = 10
_OUTBOUND_RECORD_RETENTION_SECONDS = 24 * 3600

_EXTRA_MEDIA_TYPES: dict[str, str] = {
    ".md": "text/markdown",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".m4a": "audio/mp4",
    ".opus": "audio/ogg",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".flac": "audio/flac",
    ".csv": "text/csv",
    ".json": "application/json",
}


def _sanitize_filename(name: str) -> str:
    """Remove path/control characters and cap the name while retaining suffix."""
    safe = "".join(char for char in str(name) if char not in "/\\" and unicodedata.category(char) != "Cc")
    safe = safe.lstrip(".")
    if not safe:
        return "file"

    if len(safe) > MAX_CHAT_FILENAME_LENGTH:
        stem, dot, suffix = safe.rpartition(".")
        extension = f".{suffix}" if dot else ""
        if extension and len(extension) < MAX_CHAT_FILENAME_LENGTH:
            safe = stem[: MAX_CHAT_FILENAME_LENGTH - len(extension)] + extension
        else:
            safe = safe[:MAX_CHAT_FILENAME_LENGTH]
    return safe or "file"


def guess_media_type(path: Path | str) -> str:
    """Return a best-effort media type for an outbound attachment."""
    suffix = Path(path).suffix.lower()
    if suffix in _EXTRA_MEDIA_TYPES:
        return _EXTRA_MEDIA_TYPES[suffix]
    guessed, _encoding = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _record_path(anima_dir: Path, request_id: str) -> Path:
    safe_request_id = _sanitize_filename(request_id)
    return anima_dir / "run" / "chat_attachments" / f"{safe_request_id}.jsonl"


def _read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(record, dict):
                    records.append(record)
    except FileNotFoundError:
        return []
    except OSError:
        logger.debug("Could not read chat attachment records: %s", path, exc_info=True)
        return []
    return records


def _cleanup_old_records(directory: Path) -> None:
    cutoff = time.time() - _OUTBOUND_RECORD_RETENTION_SECONDS
    try:
        entries = list(directory.iterdir())
    except FileNotFoundError:
        return
    except OSError:
        logger.debug("Could not list chat attachment records: %s", directory, exc_info=True)
        return
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            logger.debug("Could not remove stale chat attachment record: %s", entry, exc_info=True)


def stage_outbound_file(
    anima_dir: Path,
    source: Path,
    *,
    display_name: str | None,
    request_id: str,
    thread_id: str,
) -> dict[str, Any]:
    """Copy *source* into the Anima attachments directory and record it.

    Raises:
        ValueError: when the request id is missing, the source is empty or too
            large, or the request already has the maximum number of files.
    """
    if not request_id:
        raise ValueError(t("chat.attach.outbound_missing_request_id"))
    if not source.is_file():
        raise ValueError(t("chat.attach.outbound_not_file", path=str(source)))
    size = source.stat().st_size
    if size <= 0:
        raise ValueError(t("chat.attach.outbound_empty_file", name=source.name))
    if size > MAX_OUTBOUND_FILE_SIZE:
        raise ValueError(
            t(
                "chat.attach.outbound_file_too_large",
                name=source.name,
                size_mb=MAX_OUTBOUND_FILE_SIZE // (1024 * 1024),
            )
        )

    record_path = _record_path(anima_dir, request_id)
    existing_records = _read_records(record_path)
    if len(existing_records) >= MAX_OUTBOUND_FILE_COUNT:
        raise ValueError(t("chat.attach.outbound_too_many_files", count=MAX_OUTBOUND_FILE_COUNT))

    safe_name = _sanitize_filename(display_name or source.name)
    attachments_dir = anima_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now_local().strftime("%Y%m%d_%H%M%S")
    index = 1
    while True:
        filename = f"{timestamp}_a{index}_{safe_name}"
        target = attachments_dir / filename
        if not target.exists():
            break
        index += 1

    shutil.copyfile(source, target)
    record = {
        "name": safe_name,
        "path": f"attachments/{filename}",
        "size": size,
        "media_type": guess_media_type(source),
        "thread_id": thread_id,
        "ts": now_local().isoformat(),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {key: record[key] for key in ("name", "path", "size", "media_type")}


def _take_thread_records(directory: Path, skip: Path, thread_id: str, since: str) -> list[dict[str, Any]]:
    """Take records of *thread_id* staged at or after *since* from other request files.

    A tool process can carry a request id that differs from the reply's (for example a
    long-lived engine process), so its files would never be collected by id alone.
    """
    taken: list[dict[str, Any]] = []
    try:
        candidates = sorted(directory.glob("*.jsonl"))
    except OSError:
        return taken
    for path in candidates:
        if path == skip:
            continue
        records = _read_records(path)
        matched = [r for r in records if r.get("thread_id") == thread_id and str(r.get("ts") or "") >= since]
        if not matched:
            continue
        rest = [r for r in records if r not in matched]
        try:
            if rest:
                path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rest), encoding="utf-8")
            else:
                path.unlink()
        except OSError:
            logger.debug("Could not update chat attachment record: %s", path, exc_info=True)
            continue
        taken.extend(matched)
    return taken


def collect_outbound_files(
    anima_dir: Path,
    request_id: str,
    *,
    thread_id: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Return and clear the staged files for one reply request.

    With *thread_id* and *since*, files staged in the same thread during this reply under
    another request id are collected too.
    """
    directory = anima_dir / "run" / "chat_attachments"
    _cleanup_old_records(directory)
    if not request_id:
        return []

    record_path = _record_path(anima_dir, request_id)
    records = _read_records(record_path)
    try:
        record_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.debug("Could not remove chat attachment record: %s", record_path, exc_info=True)
    if thread_id and since:
        records.extend(_take_thread_records(directory, record_path, thread_id, since))

    files: list[dict[str, Any]] = []
    for record in records:
        name = record.get("name")
        path = record.get("path")
        if not isinstance(name, str) or not isinstance(path, str):
            continue
        size = record.get("size")
        media_type = record.get("media_type")
        files.append(
            {
                "name": name,
                "path": path,
                "size": size if isinstance(size, int) else 0,
                "media_type": media_type if isinstance(media_type, str) else "application/octet-stream",
            }
        )
    return files
