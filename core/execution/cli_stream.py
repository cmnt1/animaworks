from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared L2 execution path for command-line engines.

CLI engines retain their engine-specific command construction and wire-format
adapters. This class owns the common JSONL read boundary and the default
blocking ``execute()`` implementation, which collects the public normalized
``execute_streaming()`` event contract.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from core.execution.base import BaseExecutor, ExecutionResult, TokenUsage, ToolCallRecord
from core.execution.watchdog import wait_for_engine_event
from core.prompt.context import ContextTracker
from core.schemas import ImageData

logger = logging.getLogger("animaworks.execution.cli_stream")


class CLIStreamExecutor(BaseExecutor):
    """Common L2 implementation for CLI-backed engine streams.

    Subclasses provide their own command, protocol adapter, and streaming
    execution. Raw JSONL reading and stream-to-result collection are shared.
    """

    @staticmethod
    async def read_line(stream: Any) -> bytes:
        """Read one engine line under the shared event-idle watchdog."""
        return await wait_for_engine_event(stream.readline())

    @classmethod
    async def iter_lines(cls, stream: Any) -> AsyncIterator[bytes]:
        """Yield raw lines from a CLI stream until EOF."""
        while True:
            line = await cls.read_line(stream)
            if not line:
                return
            yield line

    @staticmethod
    def parse_json_line(line: str | bytes) -> dict[str, Any] | None:
        """Decode a JSONL object, ignoring blank, malformed, and non-object lines."""
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = line.strip()
        if not line:
            return None
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Ignoring non-JSON CLI output: %s", line[:200])
            return None
        return value if isinstance(value, dict) else None

    def _format_stream_exception(self, error: Exception) -> tuple[str, str]:
        """Return user-visible text and reason for an uncaught stream failure."""
        return str(error), ""

    def _stream_exception_usage(self, error: Exception) -> TokenUsage | None:
        """Return usage to retain for a stream failure, if an engine requires it."""
        return None

    def _stream_error_text(self, message: str, final_event: dict[str, Any], current_text: str) -> str:
        """Resolve an error event against any partial or completed response."""
        if final_event.get("terminal") is True or not current_text:
            return message
        return current_text

    def _stream_result_truncated(self, final_event: dict[str, Any]) -> bool:
        """Map terminal stream metadata to the blocking truncated flag."""
        return bool(final_event.get("truncated", False))

    def _on_stream_cancel(self, error: asyncio.CancelledError, events: list[dict[str, Any]]) -> None:
        """Attach observed usage and tool evidence before propagating cancellation."""
        usage = TokenUsage()
        records: list[dict[str, Any]] = []
        for event in events:
            if event.get("type") == "usage":
                usage.merge(self._token_usage(event.get("usage")))
            records.extend(event.get("tool_call_records") or [])
        error.usage = usage.to_dict()
        error.usage_already_emitted = False
        error.tool_call_records = records

    @staticmethod
    def _token_usage(value: Any) -> TokenUsage:
        if isinstance(value, TokenUsage):
            return TokenUsage(**value.to_dict())
        if not isinstance(value, dict):
            return TokenUsage()
        fields = TokenUsage.__dataclass_fields__
        return TokenUsage(**{key: int(value.get(key, 0) or 0) for key in fields})

    @staticmethod
    def _tool_records(value: Any) -> list[ToolCallRecord]:
        if not isinstance(value, list):
            return []
        records: list[ToolCallRecord] = []
        for item in value:
            if isinstance(item, ToolCallRecord):
                records.append(item)
            elif isinstance(item, dict):
                try:
                    records.append(ToolCallRecord(**item))
                except TypeError:
                    logger.debug("Ignoring malformed CLI tool record: %r", item)
        return records

    async def execute(
        self,
        prompt: str,
        system_prompt: str = "",
        tracker: ContextTracker | None = None,
        shortterm: Any | None = None,
        trigger: str = "",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        thread_id: str = "default",
    ) -> ExecutionResult:
        """Collect the normalized stream into the blocking result contract."""
        stream_tracker = tracker or ContextTracker(model=self._model_config.model)
        events: list[dict[str, Any]] = []
        try:
            async for event in self.execute_streaming(
                system_prompt=system_prompt,
                prompt=prompt,
                tracker=stream_tracker,
                images=images,
                prior_messages=prior_messages,
                trigger=trigger,
                thread_id=thread_id,
            ):
                events.append(dict(event))
        except asyncio.CancelledError as exc:
            self._on_stream_cancel(exc, events)
            raise
        except Exception as exc:
            text, reason = self._format_stream_exception(exc)
            usage = self._stream_exception_usage(exc)
            if usage is None and hasattr(exc, "usage"):
                usage = self._token_usage(exc.usage)
            records = self._tool_records(getattr(exc, "tool_call_records", None))
            return ExecutionResult(
                text=text,
                tool_call_records=records,
                usage=usage,
                error=True,
                reason=reason,
            )

        text_parts: list[str] = []
        usage = TokenUsage()
        saw_usage = False
        final_event: dict[str, Any] = {}
        error_message = ""
        error_reason = ""
        for event in events:
            event_type = event.get("type")
            if event_type == "text_delta":
                text_parts.append(str(event.get("text", "")))
            elif event_type == "usage":
                usage.merge(self._token_usage(event.get("usage")))
                saw_usage = True
            elif event_type == "error":
                error_message = str(event.get("message") or "")
                error_reason = str(event.get("reason") or "")
            elif event_type == "done":
                final_event = event

        final_usage = final_event.get("usage")
        if final_usage is not None:
            if final_event.get("usage_already_emitted"):
                # Some adapters emit turn-local deltas before the terminal
                # event; others only include the completed usage snapshot.
                pass
            elif not saw_usage:
                usage = self._token_usage(final_usage)
            else:
                usage.merge(self._token_usage(final_usage))
        full_text = final_event.get("full_text")
        result_text = str(full_text) if full_text is not None else "".join(text_parts)
        if error_message:
            result_text = self._stream_error_text(error_message, final_event, result_text)

        records = self._tool_records(final_event.get("tool_call_records"))
        if not records:
            for event in events:
                records = self._tool_records(event.get("tool_call_records"))
                if records:
                    break

        result_message = final_event.get("result_message")
        if final_usage is None and not saw_usage:
            result_usage = None
        else:
            result_usage = usage

        replied_to = final_event.get("replied_to_from_transcript", set())
        if isinstance(replied_to, (list, tuple)):
            replied_to = set(replied_to)
        elif not isinstance(replied_to, set):
            replied_to = set()

        return ExecutionResult(
            text=result_text,
            result_message=result_message,
            replied_to_from_transcript=replied_to,
            tool_call_records=records,
            usage=result_usage,
            session_rotated=bool(final_event.get("session_rotated", False)),
            session_rotation_pending=bool(final_event.get("session_rotation_pending", False)),
            truncated=self._stream_result_truncated(final_event),
            error=bool(error_message or final_event.get("error", False)),
            reason=error_reason or str(final_event.get("reason") or ""),
            force_chain=bool(final_event.get("force_chain", False)),
            task_compact_requested=bool(final_event.get("task_compact_requested", False)),
        )
