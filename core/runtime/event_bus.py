"""In-process event buffer for events emitted by an Anima main runner."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import Any


class RootEventBus:
    """Buffer Anima main events and deliver them to one active async subscriber.

    Events remain buffered while there is no subscriber. When the bounded
    buffer fills, the oldest event is discarded and the loss count is attached
    to the next event delivered to the queue.
    """

    def __init__(self, max_events: int = 1000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be at least one")
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._changed = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscriber_generation = 0
        self._dropped = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Bind thread-safe publishing to the runner's event loop."""
        self._loop = loop or asyncio.get_running_loop()

    def publish(self, event: dict[str, Any]) -> None:
        """Publish an event from the loop thread or any other thread."""
        loop = self._loop
        if loop is None:
            self._append(event)
            return
        if loop.is_closed():
            raise RuntimeError("event bus loop is closed")
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            self._append(event)
        else:
            try:
                loop.call_soon_threadsafe(self._append, event)
            except RuntimeError as exc:
                # The loop may close between is_closed() and scheduling.
                raise RuntimeError("event bus loop is unavailable") from exc

    def _append(self, event: dict[str, Any]) -> None:
        if len(self._events) == self._events.maxlen:
            self._events.popleft()
            self._dropped += 1

        queued_event = dict(event)
        if self._dropped:
            queued_event["dropped"] = int(queued_event.get("dropped", 0)) + self._dropped
            self._dropped = 0
        self._events.append(queued_event)
        self._changed.set()

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """Yield buffered events to the sole active subscriber.

        Starting a new subscription wakes and terminates any older subscription
        without consuming its remaining buffered events.
        """
        self._subscriber_generation += 1
        generation = self._subscriber_generation
        self._changed.set()
        try:
            while generation == self._subscriber_generation:
                if self._events:
                    yield self._events.popleft()
                    continue

                self._changed.clear()
                if generation != self._subscriber_generation:
                    return
                if self._events:
                    continue
                await self._changed.wait()
        finally:
            if generation == self._subscriber_generation:
                self._subscriber_generation += 1
