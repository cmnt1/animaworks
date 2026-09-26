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
    terminal: bool
    message: str
    reason: str
    stop_kind: str
    truncated: bool
    context_update: Any


_P = ParamSpec("_P")
_EventInput = TypeVar("_EventInput", bound=Mapping[str, Any])


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
        async for item in method(*args, **kwargs):
            yield as_stream_event(item)

    return wrapped
