from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Validation, storage, and prompt formatting for chat file attachments."""

import base64
import binascii
from typing import Any

from core.anima.chat_attachments import MAX_CHAT_FILENAME_LENGTH as MAX_CHAT_FILENAME_LENGTH
from core.anima.chat_attachments import _sanitize_filename
from core.i18n import t
from core.time_utils import now_local
from server.routes.chat_models import FileAttachment

MAX_CHAT_FILE_SIZE = 25 * 1024 * 1024
MAX_CHAT_FILE_COUNT = 10
MAX_CHAT_FILES_SIZE = 50 * 1024 * 1024


def _validate_files(files: list[FileAttachment]) -> tuple[str, int] | None:
    """Return a localized validation error and status code, or ``None``."""
    if len(files) > MAX_CHAT_FILE_COUNT:
        return t("chat.attach.too_many_files", count=MAX_CHAT_FILE_COUNT), 413

    total_size = 0
    for file in files:
        try:
            decoded = base64.b64decode(file.data, validate=True)
        except (binascii.Error, ValueError):
            return t("chat.attach.invalid_base64", name=file.name), 400
        if not decoded:
            return t("chat.attach.empty_file", name=file.name), 400
        if len(decoded) > MAX_CHAT_FILE_SIZE:
            return t("chat.attach.file_too_large", name=file.name, size_mb=25), 413
        total_size += len(decoded)

    if total_size > MAX_CHAT_FILES_SIZE:
        return t("chat.attach.total_too_large", size_mb=50), 413
    return None


def save_files(anima_name: str, files: list[FileAttachment]) -> list[dict[str, Any]]:
    """Save chat files and return display metadata with anima-relative paths."""
    if not files:
        return []
    from core.paths import get_data_dir

    attachments_dir = get_data_dir() / "animas" / anima_name / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)

    timestamp = now_local().strftime("%Y%m%d_%H%M%S")
    saved: list[dict[str, Any]] = []
    for index, file in enumerate(files):
        try:
            content = base64.b64decode(file.data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(t("chat.attach.invalid_base64", name=file.name)) from exc
        safe_name = _sanitize_filename(file.name)
        filename = f"{timestamp}_{index}_{safe_name}"
        (attachments_dir / filename).write_bytes(content)
        saved.append(
            {
                "name": safe_name,
                "path": f"attachments/{filename}",
                "size": len(content),
                "media_type": file.media_type,
            }
        )
    return saved


def _format_file_size(size: int) -> str:
    if size >= 1024 * 1024:
        return t("chat.attach.prompt_size_mb", size=f"{size / (1024 * 1024):.1f}")
    if size >= 1024:
        return t("chat.attach.prompt_size_kb", size=f"{size / 1024:.1f}")
    return t("chat.attach.prompt_size_bytes", size=size)


def build_file_message(message: str, files: list[dict[str, Any]]) -> str:
    """Append file names and paths to the Anima-only message context."""
    if not files:
        return message
    lines = [
        t(
            "chat.attach.prompt_item",
            name=file["name"],
            media_type=file.get("media_type") or "application/octet-stream",
            size=_format_file_size(int(file.get("size") or 0)),
            path=file["path"],
        )
        for file in files
    ]
    header = t("chat.attach.prompt_header")
    attachment_list = f"{header}\n" + "\n".join(lines)
    return f"{message}\n\n{attachment_list}" if message.strip() else attachment_list
