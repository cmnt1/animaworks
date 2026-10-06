from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""In-memory call state for Twilio phone conversations."""

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class PhoneSession:
    """State retained while a single Twilio CallSid is active."""

    call_sid: str
    anima: str
    authenticated: bool = False
    pin_failures: int = 0
    kind: Literal["inbound", "alert"] = "inbound"
    alert_id: str | None = None
    acknowledged: bool = False
    alert_repeat_done: bool = False


class PhoneSessionStore:
    """Process-local mapping from Twilio CallSid to active phone state."""

    def __init__(self) -> None:
        self._sessions: dict[str, PhoneSession] = {}

    def create(
        self,
        call_sid: str,
        anima: str,
        *,
        kind: Literal["inbound", "alert"] = "inbound",
        alert_id: str | None = None,
    ) -> PhoneSession:
        if not call_sid:
            raise ValueError("CallSid is required")
        existing = self._sessions.get(call_sid)
        if existing is not None:
            return existing
        session = PhoneSession(call_sid=call_sid, anima=anima, kind=kind, alert_id=alert_id)
        self._sessions[call_sid] = session
        return session

    def get(self, call_sid: str) -> PhoneSession | None:
        return self._sessions.get(call_sid)

    def discard(self, call_sid: str) -> PhoneSession | None:
        return self._sessions.pop(call_sid, None)

    def clear(self) -> None:
        self._sessions.clear()

    def __len__(self) -> int:
        return len(self._sessions)


phone_sessions = PhoneSessionStore()


__all__ = ["PhoneSession", "PhoneSessionStore", "phone_sessions"]
