from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""L0 contract for engine stream events.

Events remain ordinary dict-compatible values so existing consumers can keep
using ``event["type"]`` and ``event.get(...)``.  Engine streams are adapted at
their public boundary to this contract without changing their serialized
shape.
"""

from collections.abc import AsyncIterator, Callable, Mapping
from functools import wraps
from typing import Any, Literal, ParamSpec, Required, TypedDict, TypeVar, cast

from core.execution.watchdog import (
    DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS,
    Watchdog,
    install_watchdog,
    reset_watchdog,
)

StreamEventType = Literal[
    "text_delta",
    "thinking_start",
    "thinking_delta",
    "thinking_end",
    "tool_start",
    "tool_end",
    "tool_detail",
    "usage",
    "done",
    "error",
    "thinking",
    "context_update",
]


class StreamEvent(TypedDict, total=False):
    """Dict-compatible stream event shared by all execution engines."""

    type: Required[StreamEventType]
    text: str
    thinking: str
    full_text: str
    result_message: Any
    tool_name: str
    tool_id: str
    detail: str
    usage: Any
    session_id: str | None
    tool_call_records: list[dict[str, Any]]
    record: Any
    terminal: bool
    message: str
    reason: str
    stop_kind: str
    truncated: bool
    context_update: Any
    context_usage_ratio: float
    input_tokens: int
    context_window: int
    threshold: float


_P = ParamSpec("_P")
_EventInput = TypeVar("_EventInput", bound=Mapping[str, Any])
_EVENT_UNSET = object()


def text_delta_event(text: str) -> StreamEvent:
    """Build the common visible-text event."""
    return {"type": "text_delta", "text": text}


def context_update_event(
    *,
    context_usage_ratio: float,
    input_tokens: int,
    context_window: int,
    threshold: float,
) -> StreamEvent:
    """Build a context measurement event with the established wire keys."""
    return {
        "type": "context_update",
        "context_usage_ratio": context_usage_ratio,
        "input_tokens": input_tokens,
        "context_window": context_window,
        "threshold": threshold,
    }


def tool_start_event(tool_name: str, tool_id: str) -> StreamEvent:
    """Build the common tool-start event."""
    return {"type": "tool_start", "tool_name": tool_name, "tool_id": tool_id}


def tool_end_event(tool_name: str, tool_id: str, *, record: Any) -> StreamEvent:
    """Build the common tool-completion event."""
    return {"type": "tool_end", "tool_id": tool_id, "tool_name": tool_name, "record": record}


def done_event(
    full_text: str,
    *,
    result_message: Any = None,
    tool_call_records: Any = _EVENT_UNSET,
    usage: Any = _EVENT_UNSET,
    stop_kind: Any = _EVENT_UNSET,
    truncated: Any = _EVENT_UNSET,
) -> StreamEvent:
    """Build a terminal success event without changing optional key presence."""
    event: StreamEvent = {
        "type": "done",
        "full_text": full_text,
        "result_message": result_message,
    }
    if tool_call_records is not _EVENT_UNSET:
        event["tool_call_records"] = tool_call_records
    if usage is not _EVENT_UNSET:
        event["usage"] = usage
    if stop_kind is not _EVENT_UNSET:
        event["stop_kind"] = stop_kind
    if truncated is not _EVENT_UNSET:
        event["truncated"] = truncated
    return event


def error_event(message: str, *, terminal: bool = False, reason: str | None = None) -> StreamEvent:
    """Build an error event using the established public event shape."""
    event: StreamEvent = {"type": "error", "terminal": terminal, "message": message}
    if reason is not None:
        event["reason"] = reason
    return event


def as_stream_event(value: Mapping[str, Any]) -> StreamEvent:
    """Copy a stream mapping into the L0 typed-dict contract."""
    if not isinstance(value, Mapping):
        raise TypeError(f"engine stream yielded {type(value).__name__}, expected a mapping")
    event_type = value.get("type")
    if not isinstance(event_type, str):
        raise TypeError("engine stream events must have a string 'type' field")
    return cast(StreamEvent, dict(value))


def stream_events(
    method: Callable[_P, AsyncIterator[_EventInput]],
) -> Callable[_P, AsyncIterator[StreamEvent]]:
    """Adapt an async engine stream so all emitted values pass through L0."""

    @wraps(method)
    async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> AsyncIterator[StreamEvent]:
        watchdog = Watchdog(DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS)
        token = install_watchdog(watchdog)
        iterator = method(*args, **kwargs).__aiter__()
        try:
            while True:
                try:
                    item = await watchdog.wait_for(iterator.__anext__())
                except StopAsyncIteration:
                    return
                watchdog.mark_activity()
                yield as_stream_event(item)
        finally:
            reset_watchdog(token)
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                await aclose()

    return wrapped
