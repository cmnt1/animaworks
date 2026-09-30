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
    tool_input: Any
    input: Any
    tool_detail: str
    detail: str
    result: str
    result_summary: str
    is_error: bool
    usage: Any
    usage_already_emitted: bool
    session_id: str | None
    tool_call_records: list[dict[str, Any]]
    record: Any
    terminal: bool
    message: str
    reason: str
    stop_kind: str
    truncated: bool
    error: bool
    force_chain: bool
    task_compact_requested: bool
    session_rotation_pending: bool
    replied_to_from_transcript: Any
    context_update: Any
    context_usage_ratio: float
    input_tokens: int
    context_window: int
    threshold: float


_P = ParamSpec("_P")
_EventInput = TypeVar("_EventInput", bound=Mapping[str, Any])
_EVENT_UNSET = object()


def stream_event(event_type: str, **fields: Any) -> StreamEvent:
    """Build a dict-compatible event with the supplied established wire fields."""
    return cast(StreamEvent, {"type": event_type, **fields})


def text_delta_event(text: str) -> StreamEvent:
    """Build the common visible-text event."""
    return stream_event("text_delta", text=text)


def thinking_start_event() -> StreamEvent:
    """Build a thinking-block start event."""
    return stream_event("thinking_start")


def thinking_delta_event(text: str) -> StreamEvent:
    """Build an incremental thinking event."""
    return stream_event("thinking_delta", text=text)


def thinking_end_event() -> StreamEvent:
    """Build a thinking-block end event."""
    return stream_event("thinking_end")


def thinking_event(thinking: str) -> StreamEvent:
    """Build a complete thinking event."""
    return stream_event("thinking", thinking=thinking)


def context_update_event(
    *,
    context_usage_ratio: float,
    input_tokens: int,
    context_window: int,
    threshold: float,
) -> StreamEvent:
    """Build a context measurement event with the established wire keys."""
    return stream_event(
        "context_update",
        context_usage_ratio=context_usage_ratio,
        input_tokens=input_tokens,
        context_window=context_window,
        threshold=threshold,
    )


def tool_start_event(tool_name: str, tool_id: str, **fields: Any) -> StreamEvent:
    """Build a tool-start event, preserving engine-specific optional fields."""
    return stream_event("tool_start", tool_name=tool_name, tool_id=tool_id, **fields)


def tool_end_event(
    tool_name: str,
    tool_id: str,
    *,
    record: Any = _EVENT_UNSET,
    **fields: Any,
) -> StreamEvent:
    """Build a tool-completion event without adding absent optional fields."""
    event: StreamEvent = stream_event("tool_end", tool_id=tool_id, tool_name=tool_name)
    if record is not _EVENT_UNSET:
        event["record"] = record
    event.update(fields)
    return event


def tool_detail_event(
    tool_id: str,
    *,
    tool_name: Any = _EVENT_UNSET,
    detail: Any = _EVENT_UNSET,
    **fields: Any,
) -> StreamEvent:
    """Build a tool-detail event while preserving optional key presence."""
    event: StreamEvent = stream_event("tool_detail", tool_id=tool_id)
    if tool_name is not _EVENT_UNSET:
        event["tool_name"] = tool_name
    if detail is not _EVENT_UNSET:
        event["detail"] = detail
    event.update(fields)
    return event


def usage_event(usage: Any) -> StreamEvent:
    """Build a token-usage event."""
    return stream_event("usage", usage=usage)


def done_event(
    full_text: str,
    *,
    result_message: Any = None,
    tool_call_records: Any = _EVENT_UNSET,
    usage: Any = _EVENT_UNSET,
    stop_kind: Any = _EVENT_UNSET,
    truncated: Any = _EVENT_UNSET,
    **fields: Any,
) -> StreamEvent:
    """Build a terminal success event without adding absent optional keys."""
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
    event.update(fields)
    return event


def error_event(
    message: str,
    *,
    terminal: bool = False,
    reason: str | None = None,
    **fields: Any,
) -> StreamEvent:
    """Build an error event using the established public event shape."""
    event: StreamEvent = stream_event("error", terminal=terminal, message=message)
    if reason is not None:
        event["reason"] = reason
    event.update(fields)
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
