from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared event-idle watchdog for engine streams."""

import asyncio
import contextvars
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import TypeVar

DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS = 1200.0
_T = TypeVar("_T")
_current_watchdog: contextvars.ContextVar[Watchdog | None] = contextvars.ContextVar("engine_watchdog", default=None)


class Watchdog:
    """Enforce an idle timeout between engine-originated events.

    There is deliberately no total-duration limit. Calling :meth:`mark_activity`
    for an engine event resets the deadline; AnimaWorks-side keepalives must not
    call it.
    """

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = float(timeout_seconds)
        self._clock = clock or asyncio.get_running_loop().time
        self._sleep = sleep
        self._last_activity = self._clock()
        self._activity_sequence = 0
        self._activity_changed = asyncio.Event()

    @property
    def last_activity(self) -> float:
        """Monotonic timestamp of the most recent engine event."""
        return self._last_activity

    def mark_activity(self) -> None:
        """Reset the idle deadline after receiving an engine-originated event."""
        self._last_activity = self._clock()
        self._activity_sequence += 1
        self._activity_changed.set()

    def remaining(self) -> float:
        """Seconds left before the stream is considered idle."""
        return max(0.0, self.timeout_seconds - (self._clock() - self._last_activity))

    def check(self) -> None:
        """Raise ``TimeoutError`` if the event-idle deadline has elapsed."""
        if self.remaining() <= 0:
            raise TimeoutError(f"engine stream idle for {self.timeout_seconds:.0f}s")

    async def wait_for(self, awaitable: Awaitable[_T]) -> _T:
        """Await work, updating the timeout when nested readers mark activity."""
        operation = asyncio.ensure_future(awaitable)
        try:
            while not operation.done():
                remaining = self.remaining()
                if remaining <= 0:
                    raise TimeoutError(f"engine stream idle for {self.timeout_seconds:.0f}s")

                self._activity_changed.clear()
                sequence = self._activity_sequence
                timer = asyncio.create_task(self._sleep(remaining))
                changed = asyncio.create_task(self._activity_changed.wait())
                done, _ = await asyncio.wait(
                    (operation, timer, changed),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in (timer, changed):
                    if task not in done:
                        task.cancel()
                await asyncio.gather(
                    *(task for task in (timer, changed) if task not in done),
                    return_exceptions=True,
                )

                if operation in done:
                    return operation.result()
                if changed in done or self._activity_sequence != sequence:
                    continue
                if timer in done:
                    self.check()

            return operation.result()
        except BaseException:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
            raise


async def wait_for_engine_event(awaitable: Awaitable[_T]) -> _T:
    """Wait for one engine event and count it as activity.

    Raw engine readers call this before parsing a message, so CLI system and
    control-protocol messages reset the timer too. With no surrounding public
    stream decorator the same 1200-second idle bound is applied locally.
    """
    watchdog = _current_watchdog.get()
    if watchdog is None:
        watchdog = Watchdog()
        result = await watchdog.wait_for(awaitable)
    else:
        # The public stream wrapper owns the deadline and observes this reset.
        # Avoid a second concurrent timer around the same nested read.
        result = await awaitable
    watchdog.mark_activity()
    return result


async def engine_events(source: AsyncIterable[_T]) -> AsyncIterator[_T]:
    """Iterate raw engine messages with a shared event-idle deadline."""
    iterator = source.__aiter__()
    while True:
        try:
            yield await wait_for_engine_event(iterator.__anext__())
        except StopAsyncIteration:
            return


def current_watchdog() -> Watchdog | None:
    """Return the watchdog active for the current public engine stream."""
    return _current_watchdog.get()


def install_watchdog(watchdog: Watchdog) -> contextvars.Token[Watchdog | None]:
    """Install a watchdog in the current async context."""
    return _current_watchdog.set(watchdog)


def reset_watchdog(token: contextvars.Token[Watchdog | None]) -> None:
    """Restore the previous watchdog context."""
    _current_watchdog.reset(token)
