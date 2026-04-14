from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""In-memory auth alert registry.

When an executor detects an auth failure (expired token, invalid credentials),
it records an alert here.  The dashboard polls ``get_alerts()`` and renders
provider-specific warnings with re-login buttons.

Alerts are cleared when the user triggers a re-login via the dashboard, or
when the provider successfully authenticates again.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any

_lock = threading.Lock()


@dataclass
class AuthAlert:
    """A single auth failure alert for a provider."""

    provider: str  # "claude", "openai", "nanogpt"
    message: str
    anima_name: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "message": self.message,
            "anima_name": self.anima_name,
            "timestamp": self.timestamp,
        }


_alerts: dict[str, AuthAlert] = {}


def raise_alert(provider: str, message: str, *, anima_name: str = "") -> None:
    """Record an auth failure for *provider* (overwrites previous alert)."""
    with _lock:
        _alerts[provider] = AuthAlert(
            provider=provider,
            message=message,
            anima_name=anima_name,
        )


def clear_alert(provider: str) -> None:
    """Clear the auth alert for *provider* (e.g. after successful re-login)."""
    with _lock:
        _alerts.pop(provider, None)


def get_alerts() -> list[dict[str, Any]]:
    """Return all active auth alerts as dicts."""
    with _lock:
        return [a.to_dict() for a in _alerts.values()]


def has_alert(provider: str) -> bool:
    """Check if there is an active alert for *provider*."""
    with _lock:
        return provider in _alerts
