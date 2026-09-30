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


def test_event_constructors_preserve_wire_fields_and_optional_keys() -> None:
    from core.execution.events import (
        context_update_event,
        done_event,
        error_event,
        stream_event,
        text_delta_event,
        thinking_delta_event,
        thinking_end_event,
        thinking_event,
        thinking_start_event,
        tool_detail_event,
        tool_end_event,
        tool_start_event,
        usage_event,
    )

    assert text_delta_event("hello") == {"type": "text_delta", "text": "hello"}
    assert thinking_start_event() == {"type": "thinking_start"}
    assert thinking_delta_event("hidden") == {"type": "thinking_delta", "text": "hidden"}
    assert thinking_end_event() == {"type": "thinking_end"}
    assert thinking_event("reasoning") == {"type": "thinking", "thinking": "reasoning"}
    assert context_update_event(
        context_usage_ratio=0.5,
        input_tokens=50,
        context_window=100,
        threshold=0.8,
    ) == {
        "type": "context_update",
        "context_usage_ratio": 0.5,
        "input_tokens": 50,
        "context_window": 100,
        "threshold": 0.8,
    }
    assert tool_start_event("Read", "tool-1", input={"path": "a.txt"}) == {
        "type": "tool_start",
        "tool_name": "Read",
        "tool_id": "tool-1",
        "input": {"path": "a.txt"},
    }
    assert tool_end_event("Read", "tool-1") == {
        "type": "tool_end",
        "tool_id": "tool-1",
        "tool_name": "Read",
    }
    assert tool_end_event("Read", "tool-1", record=None) == {
        "type": "tool_end",
        "tool_id": "tool-1",
        "tool_name": "Read",
        "record": None,
    }
    assert tool_detail_event("tool-1", tool_name="Read", detail="a.txt") == {
        "type": "tool_detail",
        "tool_id": "tool-1",
        "tool_name": "Read",
        "detail": "a.txt",
    }
    assert usage_event({"input_tokens": 12}) == {"type": "usage", "usage": {"input_tokens": 12}}
    assert done_event("hello") == {
        "type": "done",
        "full_text": "hello",
        "result_message": None,
    }
    assert done_event("hello", result_message=None, stop_kind="normal", usage={}) == {
        "type": "done",
        "full_text": "hello",
        "result_message": None,
        "usage": {},
        "stop_kind": "normal",
    }
    assert error_event("failed") == {"type": "error", "terminal": False, "message": "failed"}
    assert stream_event("error", message="failed") == {"type": "error", "message": "failed"}


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
