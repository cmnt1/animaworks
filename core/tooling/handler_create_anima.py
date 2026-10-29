from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tooling._handler_protocols import _CreateAnimaHost

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CreateAnimaMixin — request root-owned anima creation from a character sheet."""

import logging

from core.tooling.handler_base import _error_result

logger = logging.getLogger("animaworks.tool_handler")


class CreateAnimaMixin:
    """Mixin for create_anima tool handler."""

    def _handle_create_anima(self: _CreateAnimaHost, args: dict[str, Any]) -> str:
        """Create a new anima through the root's authenticated internal API."""
        content = args.get("character_sheet_content")
        sheet_path_raw = args.get("character_sheet_path")
        name = args.get("name")
        supervisor = args.get("supervisor")
        md_path: Path | None = None

        if content:
            content = str(content)
        elif sheet_path_raw:
            md_path = Path(sheet_path_raw).expanduser()
            if not md_path.is_absolute():
                anima_dir = self._tool_context.anima_dir
                md_path = (anima_dir / md_path).resolve()
                if not md_path.is_relative_to(anima_dir.resolve()):
                    return _error_result(
                        "PermissionDenied",
                        "character_sheet_path must be within anima directory.",
                    )
            else:
                # Absolute paths are intentionally supported for operator-provided files.
                # The root API performs full character-sheet validation before writing.
                md_path = md_path.resolve()
            if not md_path.exists():
                return _error_result(
                    "FileNotFound",
                    f"Character sheet not found: {md_path}",
                    suggestion="Use character_sheet_content to pass content directly, or ensure the file exists",
                )
            # Prefer in-memory content so sandbox-local paths do not need to be
            # visible to root. If the worker cannot read it, pass the path instead.
            try:
                content = md_path.read_text(encoding="utf-8")
            except OSError:
                content = None
        else:
            return _error_result(
                "MissingParameter",
                "Either character_sheet_content or character_sheet_path is required",
            )

        payload: dict[str, Any] = {
            "calling_anima": self._tool_context.anima_name or "",
        }
        if content is not None:
            payload["character_sheet_content"] = content
        elif md_path is not None:
            payload["character_sheet_path"] = str(md_path)
        if name:
            payload["name"] = name
        if supervisor:
            payload["supervisor"] = supervisor

        from core.host_api import host_api, response_detail

        try:
            response = host_api.post("/api/internal/anima/create", json=payload, timeout=60.0)
        except Exception as exc:
            logger.warning("create_anima: root API request failed", exc_info=True)
            return _error_result("PermissionDenied", f"Cannot create anima: root API unreachable ({exc})")

        detail = response_detail(response)
        if response.status_code == 409:
            return _error_result("AnimaExists", detail, suggestion="Choose a different name")
        if response.status_code == 422:
            return _error_result("InvalidCharacterSheet", detail)
        if response.status_code >= 400:
            return _error_result("PermissionDenied", f"Cannot create anima: root API failed ({detail})")

        try:
            data = response.json()
        except Exception:
            data = {}
        anima_dir_str = data.get("anima_dir", "") if isinstance(data, dict) else ""
        anima_name = Path(anima_dir_str).name if anima_dir_str else (name or "unknown")
        logger.info("create_anima: created '%s' via root API at %s", anima_name, anima_dir_str)
        return f"Anima '{anima_name}' created successfully at {anima_dir_str}. Reload the server to activate."
