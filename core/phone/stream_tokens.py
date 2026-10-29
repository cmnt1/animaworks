from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Short-lived, one-use credentials for authenticated Twilio Media Streams."""

import hmac
import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _StreamToken:
    call_sid: str
    expires_at: float


class PhoneStreamTokenStore:
    """In-memory store for CallSid-bound tokens consumed by one WS connection."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        max_items: int = 10_000,
        clock=time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._clock = clock
        self._tokens: dict[str, _StreamToken] = {}
        self._lock = threading.Lock()

    def issue(self, call_sid: str) -> str:
        """Create an opaque one-time token valid only for ``call_sid``."""
        if not call_sid:
            raise ValueError("CallSid is required")
        now = self._clock()
        with self._lock:
            self._prune(now)
            while len(self._tokens) >= self._max_items:
                oldest = min(self._tokens, key=lambda token: self._tokens[token].expires_at)
                self._tokens.pop(oldest, None)
            token = secrets.token_urlsafe(32)
            self._tokens[token] = _StreamToken(call_sid=call_sid, expires_at=now + self._ttl_seconds)
            return token

    def consume(self, token: str, call_sid: str) -> bool:
        """Consume a valid token once; a mismatched CallSid does not consume it."""
        if not token or not call_sid:
            return False
        now = self._clock()
        with self._lock:
            entry = self._tokens.get(token)
            if entry is None:
                return False
            if entry.expires_at <= now:
                self._tokens.pop(token, None)
                return False
            if not hmac.compare_digest(entry.call_sid, call_sid):
                return False
            self._tokens.pop(token, None)
            return True

    def revoke_for_call(self, call_sid: str) -> None:
        """Revoke all outstanding credentials belonging to a completed call."""
        if not call_sid:
            return
        with self._lock:
            for token, entry in list(self._tokens.items()):
                if entry.call_sid == call_sid:
                    self._tokens.pop(token, None)

    def clear(self) -> None:
        """Clear all credentials; primarily used by tests and process teardown."""
        with self._lock:
            self._tokens.clear()

    def __len__(self) -> int:
        with self._lock:
            self._prune(self._clock())
            return len(self._tokens)

    def _prune(self, now: float) -> None:
        for token, entry in list(self._tokens.items()):
            if entry.expires_at <= now:
                self._tokens.pop(token, None)


phone_stream_tokens = PhoneStreamTokenStore()


__all__ = ["PhoneStreamTokenStore", "phone_stream_tokens"]
