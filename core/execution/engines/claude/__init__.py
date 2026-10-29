from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Mode S: Claude Agent SDK executor and its hooks, options, session and stream handling."""

from core.execution.engines.claude._sdk_patch import apply_sdk_transport_patch


def resolve_sdk_cli_path() -> str | None:
    """Return the verified Claude CLI path through the engine's public API."""
    from core.execution.engines.claude._sdk_options import _resolve_sdk_cli_path

    return _resolve_sdk_cli_path()


apply_sdk_transport_patch()
