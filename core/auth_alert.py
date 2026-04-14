from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""File-based auth alert registry (cross-process).

When an executor detects an auth failure (expired token, invalid credentials),
it records an alert here.  The dashboard polls ``get_alerts()`` and renders
provider-specific warnings with re-login buttons.

Alerts are persisted to ``~/.animaworks/run/auth_alerts.json`` so they are
visible across the server process and Anima child processes.

Alerts are cleared when the user triggers a re-login via the dashboard, or
when the provider successfully authenticates again.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("animaworks.auth_alert")


def _alert_file() -> Path:
    from core.paths import get_data_dir

    p = get_data_dir() / "run" / "auth_alerts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_alerts() -> dict[str, Any]:
    """Read all alerts from disk."""
    path = _alert_file()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_alerts(alerts: dict[str, Any]) -> None:
    """Write all alerts to disk atomically."""
    path = _alert_file()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(alerts, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        logger.debug("Failed to write auth alerts", exc_info=True)


def raise_alert(provider: str, message: str, *, anima_name: str = "") -> None:
    """Record an auth failure for *provider* (overwrites previous alert)."""
    alerts = _read_alerts()
    alerts[provider] = {
        "provider": provider,
        "message": message,
        "anima_name": anima_name,
        "timestamp": time.time(),
    }
    _write_alerts(alerts)


def clear_alert(provider: str) -> None:
    """Clear the auth alert for *provider* (e.g. after successful re-login)."""
    alerts = _read_alerts()
    if provider in alerts:
        del alerts[provider]
        _write_alerts(alerts)


def get_alerts() -> list[dict[str, Any]]:
    """Return all active auth alerts as dicts."""
    alerts = _read_alerts()
    return list(alerts.values())


def has_alert(provider: str) -> bool:
    """Check if there is an active alert for *provider*."""
    return provider in _read_alerts()
