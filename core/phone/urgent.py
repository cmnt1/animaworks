from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Urgent phone alert request shared by the call_human tool and CLI."""

import logging

logger = logging.getLogger(__name__)


def request_phone_alert(subject: str, body: str, anima_name: str) -> str:
    """Best-effort urgent phone alert through the authenticated server API.

    Returns a one-line ``phone: ...`` status. Never raises: phone failure is
    independent of the other notification channels.
    """
    from core.internal_api import host_api

    try:
        response = host_api.post(
            "/api/internal/phone/alert",
            json={"anima": anima_name, "subject": subject, "body": body},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return "phone: ERROR - invalid server response"
        status = payload.get("status")
        if status == "calling":
            return "phone: calling"
        if status == "skipped":
            reason = str(payload.get("reason") or "not configured").replace("\n", " ")[:200]
            return f"phone: skipped ({reason})"
        return "phone: ERROR - unexpected server response"
    except Exception as exc:
        # Keep provider/network exception details out of tool output: they can
        # contain request metadata.
        logger.warning("urgent phone alert request failed (%s)", type(exc).__name__)
        return f"phone: ERROR - {type(exc).__name__}"


__all__ = ["request_phone_alert"]
