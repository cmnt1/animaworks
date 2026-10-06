from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Short-lived in-memory storage for generated phone audio."""

import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _AudioEntry:
    data: bytes
    expires_at: float


class AudioStore:
    """Keep WAV bytes behind unguessable, expiring tokens."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 3600,
        max_items: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_items < 1:
            raise ValueError("max_items must be at least one")
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._clock = clock
        self._items: OrderedDict[str, _AudioEntry] = OrderedDict()

    def put(self, data: bytes) -> str:
        """Store *data* and return a URL-safe, unguessable token."""
        if not data:
            raise ValueError("audio data must not be empty")
        self._prune_expired()
        token = secrets.token_urlsafe(24)
        while token in self._items:
            token = secrets.token_urlsafe(24)
        self._items[token] = _AudioEntry(data=bytes(data), expires_at=self._clock() + self._ttl_seconds)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)
        return token

    def get(self, token: str) -> bytes | None:
        """Return stored audio, or ``None`` when missing or expired."""
        self._prune_expired()
        entry = self._items.get(token)
        if entry is None:
            return None
        self._items.move_to_end(token)
        return entry.data

    def clear(self) -> None:
        """Remove all cached audio (primarily useful for tests/shutdown)."""
        self._items.clear()

    def __len__(self) -> int:
        self._prune_expired()
        return len(self._items)

    def _prune_expired(self) -> None:
        now = self._clock()
        expired = [token for token, entry in self._items.items() if entry.expires_at <= now]
        for token in expired:
            self._items.pop(token, None)


phone_audio_store = AudioStore()


__all__ = ["AudioStore", "phone_audio_store"]
