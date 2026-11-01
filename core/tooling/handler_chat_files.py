from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""ChatFilesToolsMixin — attach a local file to the current web-chat reply."""

import json
import logging
from pathlib import Path
from typing import Any

from core.anima.chat_attachments import stage_outbound_file
from core.execution.session.session_context import current_runtime_session
from core.i18n import t
from core.tooling._handler_protocols import _ChatFilesHost
from core.tooling.handler_base import _error_result
from core.tooling.policy.surface import chat_attachments_enabled_for_trigger

logger = logging.getLogger("animaworks.tool_handler")


class ChatFilesToolsMixin:
    """Stage files that should accompany a chat response."""

    _anima_dir: Path
    _runtime_session_context: Any
    _check_file_permission: Any

    def _handle_attach_file(self: _ChatFilesHost, args: dict[str, Any]) -> str:
        raw_path = args.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return _error_result("InvalidArguments", t("tooling.attach_file.path_required"))

        source = Path(raw_path).expanduser()
        if not source.is_absolute():
            source = self._anima_dir / source
        try:
            source = source.resolve()
        except OSError:
            pass

        err = self._check_file_permission(str(source))
        if err:
            return err
        if not source.is_file():
            return _error_result(
                "FileNotFound",
                t("tooling.attach_file.not_found", path=str(source)),
                suggestion=t("tooling.attach_file.not_found_suggestion"),
            )

        ctx = current_runtime_session() or self._runtime_session_context
        if ctx is None or not chat_attachments_enabled_for_trigger(ctx.trigger):
            return _error_result(
                "ToolBlocked",
                t("tooling.attach_file.chat_only"),
                suggestion=t("tooling.attach_file.chat_only_suggestion"),
            )

        display_name = args.get("name")
        if display_name is not None and not isinstance(display_name, str):
            return _error_result("InvalidArguments", t("tooling.attach_file.invalid_name"))

        try:
            attached = stage_outbound_file(
                self._anima_dir,
                source,
                display_name=display_name or None,
                request_id=ctx.request_id,
                thread_id=ctx.thread_id,
            )
        except ValueError as exc:
            return _error_result("InvalidArguments", str(exc))
        except OSError as exc:
            logger.warning("Could not stage chat attachment %s: %s", source, exc)
            return _error_result("FileIOError", t("tooling.attach_file.stage_failed", error=str(exc)))

        return json.dumps(
            {
                "status": "ok",
                "attached": attached,
                "message": t("tooling.attach_file.attached", name=attached["name"]),
            },
            ensure_ascii=False,
        )
