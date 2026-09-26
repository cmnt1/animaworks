from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from core.execution.events import StreamEvent, as_stream_event, stream_events


def test_as_stream_event_preserves_dict_shape_and_values() -> None:
    nested = {"prompt_tokens": 12}
    original = {"type": "usage", "usage": nested, "extra": True}

    result: StreamEvent = as_stream_event(original)

    assert isinstance(result, dict)
    assert result == original
    assert result is not original
    assert result["usage"] is nested


def test_as_stream_event_requires_a_string_type() -> None:
    with pytest.raises(TypeError, match="string 'type'"):
        as_stream_event({"text": "missing type"})


@pytest.mark.asyncio
async def test_stream_events_adapts_generator_values_through_l0() -> None:
    @stream_events
    async def source() -> AsyncIterator[dict[str, Any]]:
        yield {"type": "text_delta", "text": "hello"}
        yield {"type": "done", "full_text": "hello"}

    events = [event async for event in source()]

    assert events == [
        {"type": "text_delta", "text": "hello"},
        {"type": "done", "full_text": "hello"},
    ]
    assert all(isinstance(event, dict) for event in events)
