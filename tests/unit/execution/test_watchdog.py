from __future__ import annotations

import asyncio

import pytest

from core.execution.events import stream_events
from core.execution.watchdog import DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS, Watchdog, wait_for_engine_event


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_watchdog_times_out_after_1200_seconds_without_engine_events() -> None:
    clock = FakeClock()
    watchdog = Watchdog(clock=clock, sleep=clock.sleep)

    with pytest.raises(TimeoutError, match="1200s"):
        await watchdog.wait_for(asyncio.Future())

    assert clock.now >= DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_watchdog_allows_multi_hour_stream_with_events_every_1190_seconds() -> None:
    clock = FakeClock()
    watchdog = Watchdog(clock=clock, sleep=asyncio.sleep)

    for _ in range(120):  # nearly 40 hours of total engine activity

        async def next_event() -> str:
            clock.now += 1190
            return "event"

        assert await watchdog.wait_for(next_event()) == "event"
        watchdog.mark_activity()
        watchdog.check()

    assert clock.now == 120 * 1190


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["S", "C", "D", "G", "X", "A"])
async def test_public_engine_stream_accepts_multi_hour_event_activity(
    engine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del engine  # All engine adapters share the public L0 stream watchdog.
    clock = FakeClock()
    monkeypatch.setattr(
        "core.execution.events.Watchdog",
        lambda timeout: Watchdog(timeout, clock=clock, sleep=asyncio.sleep),
    )

    @stream_events
    async def fake_engine():
        for _ in range(120):
            clock.now += 1190
            await wait_for_engine_event(asyncio.sleep(0, result={"type": "system"}))
        yield {"type": "done"}

    events = [event async for event in fake_engine()]

    assert events == [{"type": "done"}]
    assert clock.now == 120 * 1190


@pytest.mark.asyncio
async def test_public_engine_stream_times_out_after_1200_seconds_without_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(
        "core.execution.events.Watchdog",
        lambda timeout: Watchdog(timeout, clock=clock, sleep=clock.sleep),
    )

    @stream_events
    async def silent_engine():
        await asyncio.Future()
        yield {"type": "done"}

    with pytest.raises(TimeoutError, match="1200s"):
        async for _ in silent_engine():
            pass

    assert clock.now >= DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS
