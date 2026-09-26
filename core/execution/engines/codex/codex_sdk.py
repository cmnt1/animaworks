from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Mode C executor: Codex Python SDK (Codex App Server wrapper).

Runs OpenAI models via the Codex App Server as an autonomous agent.  The SDK
spawns the Codex binary and exchanges JSON-RPC notifications over stdio. Tool
safety relies on Codex's sandbox mode plus MCP integration with AnimaWorks
``core/mcp/server.py`` for permission-checked tool access.

System prompt is injected via ``model_instructions_file`` in a per-anima
CODEX_HOME directory.  Session resume uses the Codex SDK's ``thread_resume``
mechanism with thread IDs persisted to the shortterm directory.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from core.execution.base import (
    ExecutionResult,
    StreamDisconnectedError,
    TokenUsage,
    ToolCallRecord,
)
from core.execution.cli_stream import CLIStreamExecutor
from core.execution.events import stream_events
from core.execution.session_context import _resolve_session_type
from core.execution.session_store import SessionRecord, SessionStore
from core.execution.session_types import is_persistent_codex_session
from core.execution.tool_evidence import ToolEvidence
from core.execution.watchdog import DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS, wait_for_engine_event
from core.prompt.context import ContextTracker
from core.schemas import ImageData, ModelConfig

from . import events, setup

logger = logging.getLogger("animaworks.execution.codex_sdk")

__all__ = ["CodexSDKExecutor", "clear_codex_thread_id", "clear_codex_thread_ids"]

RESUME_TIMEOUT_SEC = 15.0
_RESUME_PROMPT_SIZE_LIMIT = 50_000
_FATAL_STDERR_PATTERNS = ("error: stream closed",)

# ── Session (thread) ID persistence ──────────────────────────


def _thread_id_path(anima_dir: Path, session_type: str, chat_thread_id: str = "default") -> Path:
    return SessionStore.path_for("codex", anima_dir, session_type, chat_thread_id)


def _save_thread_id(anima_dir: Path, thread_id: str, session_type: str, chat_thread_id: str = "default") -> None:
    SessionStore(_thread_id_path(anima_dir, session_type, chat_thread_id)).write_text_record(
        SessionRecord(thread_id),
        with_turn_count=False,
    )


def _load_thread_id(anima_dir: Path, session_type: str, chat_thread_id: str = "default") -> str | None:
    record = SessionStore(_thread_id_path(anima_dir, session_type, chat_thread_id)).read_text_record(
        with_turn_count=False,
    )
    return record.session_id if record is not None else None


def _clear_thread_id(anima_dir: Path, session_type: str, chat_thread_id: str = "default") -> None:
    SessionStore(_thread_id_path(anima_dir, session_type, chat_thread_id)).clear()


def clear_codex_thread_id(anima_dir: Path, session_type: str, chat_thread_id: str = "default") -> None:
    """Clear one resolved Codex thread ID namespace."""
    _clear_thread_id(anima_dir, session_type, chat_thread_id)


def clear_codex_thread_ids(anima_dir: Path, chat_thread_id: str = "default") -> None:
    """Clear persisted Codex thread IDs for all known runtime session types."""
    for st in ("chat", "heartbeat", "cron", "task", "inbox"):
        _clear_thread_id(anima_dir, st, chat_thread_id)


# ── Helpers ──────────────────────────────────────────────────


def _stderr_contains_fatal_signal(text: str) -> bool:
    """Return True when Codex stderr already indicates the stream is unrecoverable."""
    lowered = text.lower()
    return any(pattern in lowered for pattern in _FATAL_STDERR_PATTERNS)


def _should_cli_exec_fallback(exc: BaseException) -> bool:
    """Return True when the Codex SDK is failing in a way the CLI exec path can bypass."""
    cur: BaseException | None = exc
    while cur is not None:
        lowered = str(cur).lower()
        if "fatal stderr signal" in lowered:
            return True
        if "stream closed" in lowered:
            return True
        if "reading prompt from stdin" in lowered:
            return True
        cur = cur.__cause__ or cur.__context__
        if cur is exc:
            break
    return False


def _is_limit_overrun(exc: BaseException) -> bool:
    """Check whether *exc* or its cause chain contains a buffer overflow."""
    cur: BaseException | None = exc
    while cur is not None:
        name = type(cur).__name__
        if "LimitOverrunError" in name:
            return True
        msg = str(cur)
        if "chunk exceed the limit" in msg or "Separator is not found" in msg:
            return True
        cur = cur.__cause__ or cur.__context__
        if cur is exc:
            break
    return False


class CodexSDKExecutor(events.CodexEventsMixin, CLIStreamExecutor):
    """Execute via Codex SDK (Mode C).

    The SDK spawns the Codex CLI as a subprocess.  Tool access is secured by
    Codex's ``sandbox_mode`` and MCP integration with ``core/mcp/server.py``.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        anima_dir: Path,
        tool_registry: list[str] | None = None,
        personal_tools: dict[str, str] | None = None,
        interrupt_event: asyncio.Event | None = None,
        codex_home: Path | None = None,
    ) -> None:
        super().__init__(model_config, anima_dir, interrupt_event=interrupt_event)
        self._tool_registry = tool_registry or []
        self._personal_tools = personal_tools or {}
        self._codex_home = codex_home or anima_dir / ".codex_home"

    @property
    def supports_streaming(self) -> bool:  # noqa: D102
        return True

    def _format_stream_exception(self, error: Exception) -> tuple[str, str]:
        logger.exception("Codex execution failed after observed usage")
        metadata = events._codex_error_metadata(str(error), self._model_config.model)
        return f"[Codex SDK Error: {error}]", str(metadata.get("reason") or "")

    def _stream_exception_usage(self, error: Exception) -> TokenUsage | None:
        return self._token_usage(error.usage) if hasattr(error, "usage") else TokenUsage()

    def _stream_error_text(self, message: str, final_event: dict[str, Any], current_text: str) -> str:
        return current_text or message

    def _stream_result_truncated(self, final_event: dict[str, Any]) -> bool:
        return final_event.get("stop_kind") == "interrupted"

    def _on_stream_cancel(self, error: asyncio.CancelledError, stream_events: list[dict[str, Any]]) -> None:
        evidence = ToolEvidence()
        usage = TokenUsage()
        for event in stream_events:
            evidence.observe(event)
            if event.get("type") == "usage":
                usage.merge(events._token_usage(event.get("usage") or {}))
        evidence.merge(getattr(error, "tool_call_records", None) or [])
        error.usage = usage.to_dict()
        error.usage_already_emitted = False
        error.tool_call_records = evidence.to_dicts()

    async def _execute_via_cli_exec(
        self,
        prompt: str,
        system_prompt: str,
        tracker: ContextTracker | None = None,
        trigger: str = "",
    ) -> ExecutionResult:
        """Blocking wrapper around the CLI exec fallback path."""
        tracker = tracker or ContextTracker(model=self._model_config.model)
        final_event: dict[str, Any] | None = None
        usage_acc = TokenUsage()
        tool_evidence = ToolEvidence()
        try:
            async for ev in self._execute_streaming_via_cli_exec(system_prompt, prompt, tracker, trigger=trigger):
                tool_evidence.observe(ev)
                if ev.get("type") == "usage":
                    usage_acc.merge(events._token_usage(ev.get("usage") or {}))
                elif ev.get("type") == "done":
                    final_event = ev
                    if not ev.get("usage_already_emitted"):
                        usage_acc.merge(events._token_usage(ev.get("usage") or {}))
        except BaseException as exc:
            if isinstance(exc, (Exception, asyncio.CancelledError)):
                exc.usage = usage_acc.to_dict()
                exc.usage_already_emitted = False
                tool_evidence.merge(getattr(exc, "tool_call_records", None) or [])
                exc.tool_call_records = tool_evidence.to_dicts()
            raise
        if final_event is None:
            return ExecutionResult(
                text="[Codex CLI exec fallback returned no result]",
                usage=usage_acc,
                error=True,
                tool_call_records=[ToolCallRecord(**record) for record in tool_evidence.to_dicts()],
            )
        return ExecutionResult(
            text=str(final_event.get("full_text", "")),
            result_message=final_event.get("result_message"),
            replied_to_from_transcript=final_event.get("replied_to_from_transcript", set()),
            tool_call_records=[ToolCallRecord(**record) for record in tool_evidence.to_dicts()],
            usage=usage_acc,
        )

    async def _start_or_resume_thread(
        self,
        codex: Any,
        thread_id: str | None,
        session_type: str,
        system_prompt: str,
        chat_thread_id: str = "default",
        persist_thread: bool = True,
    ) -> Any:
        """Start a new thread or attempt to resume an existing one."""
        thread_kwargs = self._codex_thread_kwargs(system_prompt)
        if thread_id:
            try:
                thread = await setup._maybe_await(codex.thread_resume(thread_id, **thread_kwargs))
                logger.info("Resumed Codex thread %s", thread_id)
                return thread
            except Exception as e:
                logger.warning(
                    "Codex thread resume failed (thread_id=%s): %s. Starting fresh thread.",
                    thread_id,
                    e,
                )
                if persist_thread:
                    _clear_thread_id(self._anima_dir, session_type, chat_thread_id)
        thread = await setup._maybe_await(codex.thread_start(**thread_kwargs))
        logger.info("Started fresh Codex thread")
        return thread

    def discard_thread(
        self,
        session_type: str = "chat",
        chat_thread_id: str = "default",
    ) -> None:
        """Discard Codex thread ID so next session starts fresh."""
        _clear_thread_id(self._anima_dir, session_type, chat_thread_id)
        logger.info(
            "Discarded Codex thread for %s (session=%s, thread=%s)",
            self._anima_dir.name,
            session_type,
            chat_thread_id,
        )

    @stream_events
    async def execute_streaming(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        trigger: str = "",
        thread_id: str = "default",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream events from Codex SDK.

        Handles the full Codex event lifecycle for progressive streaming:

        - ``item.started`` / ``item.updated``: emit incremental text deltas
          by tracking per-item text length and yielding only the new portion.
        - ``item.completed``: emit any remaining text delta and tool records.
        - ``turn.completed``: update context tracker with usage stats.
        - ``turn.failed`` / ``error``: propagate as error events.

        Yields dicts:
            ``{"type": "text_delta", "text": "..."}``
            ``{"type": "tool_start", "tool_name": "...", "tool_id": "..."}``
            ``{"type": "tool_end", "tool_id": "...", "tool_name": "..."}``
            ``{"type": "tool_detail", "tool_id": "...", ...}``
            ``{"type": "done", "full_text": "...", "result_message": ...}``
        """
        if self._check_interrupted():
            yield {"type": "text_delta", "text": "[Session interrupted by user]"}
            yield {
                "type": "done",
                "full_text": "[Session interrupted by user]",
                "result_message": None,
                "stop_kind": "interrupted",
            }
            return

        if setup._should_prefer_cli_exec(trigger):
            logger.info("Using `codex exec` streaming directly for trigger=%s", trigger)
            async for ev in self._execute_streaming_via_cli_exec(system_prompt, prompt, tracker, trigger=trigger):
                yield ev
            return

        session_type = _resolve_session_type(trigger)
        chat_thread_id = thread_id
        persist_thread = is_persistent_codex_session(trigger)
        if persist_thread:
            codex_thread_id = _load_thread_id(self._anima_dir, session_type, chat_thread_id)
        else:
            clear_codex_thread_id(self._anima_dir, session_type, chat_thread_id)
            codex_thread_id = None

        prompt_bytes = len(system_prompt.encode("utf-8"))
        if codex_thread_id and SessionStore.prompt_size_exceeded(prompt_bytes, _RESUME_PROMPT_SIZE_LIMIT):
            logger.info(
                "Skipping Codex resume (prompt=%d bytes > %d limit) to avoid LimitOverrunError; using fresh thread",
                prompt_bytes,
                _RESUME_PROMPT_SIZE_LIMIT,
            )
            codex_thread_id = None

        self._write_codex_config(system_prompt)
        codex = self._create_codex_client()

        response_item_order: list[str] = []
        response_text_by_item: dict[str, str] = {}
        all_tool_records: list[ToolCallRecord] = []
        tool_evidence = ToolEvidence(self._anima_dir)
        turn_result: Any = None
        active_thread: Any = None
        usage_acc = TokenUsage()
        completed_turn_count = 0
        thinking_started = False
        interrupted = False

        def _current_full_text() -> str:
            return "\n".join(
                response_text_by_item[item_id] for item_id in response_item_order if response_text_by_item[item_id]
            )

        def _remember_agent_delta(item_id: str, delta: str) -> None:
            if not item_id:
                item_id = f"agent-{len(response_item_order) + 1}"
            if item_id not in response_text_by_item:
                response_item_order.append(item_id)
                response_text_by_item[item_id] = ""
            response_text_by_item[item_id] += delta

        def _set_agent_text(item_id: str, text: str) -> None:
            if not item_id:
                item_id = f"agent-{len(response_item_order) + 1}"
            if item_id not in response_text_by_item:
                response_item_order.append(item_id)
            response_text_by_item[item_id] = text

        def _thinking_delta_chunks(text: str) -> list[dict[str, Any]]:
            nonlocal thinking_started
            if not text:
                return []
            chunks: list[dict[str, Any]] = []
            if not thinking_started:
                thinking_started = True
                chunks.append({"type": "thinking_start"})
            chunks.append({"type": "thinking_delta", "text": text})
            return chunks

        def _thinking_end_chunk() -> dict[str, Any] | None:
            nonlocal thinking_started
            if not thinking_started:
                return None
            thinking_started = False
            return {"type": "thinking_end"}

        async def _stream_turn(tid: str | None) -> AsyncGenerator[dict[str, Any], None]:
            nonlocal completed_turn_count, turn_result, active_thread, interrupted
            thread = await self._start_or_resume_thread(
                codex,
                tid,
                session_type,
                system_prompt,
                chat_thread_id,
                persist_thread,
            )
            active_thread = thread
            usage_meter = events._CodexUsageAccumulator(fresh_thread=not tid or events._get_thread_id(thread) != tid)
            turn = await setup._maybe_await(thread.turn(prompt, **self._codex_turn_kwargs()))
            stream = turn.stream()
            event_iter = stream.__aiter__()
            item_text_len: dict[str, int] = {}
            agent_delta_seen: set[str] = set()
            tool_started: set[str] = set()
            tool_ended: set[str] = set()

            def _tool_start_chunk(tool_id: str, tool_name: str) -> dict[str, Any] | None:
                tool_evidence.started(tool_id, tool_name)
                if not tool_id or tool_id in tool_started:
                    return None
                tool_started.add(tool_id)
                return {
                    "type": "tool_start",
                    "tool_name": tool_name,
                    "tool_id": tool_id,
                }

            def _tool_detail_chunk(tool_id: str, tool_name: str, detail: str) -> dict[str, Any] | None:
                if not detail:
                    return None
                return {
                    "type": "tool_detail",
                    "tool_id": tool_id,
                    "tool_name": tool_name,
                    "detail": detail,
                }

            def _usage_from_raw(raw_usage: Any) -> dict[str, Any] | None:
                if not raw_usage:
                    return None
                delta = usage_meter.update(raw_usage)
                usage_acc.merge(delta)
                if any(delta.to_dict().values()):
                    return {"type": "usage", "usage": delta.to_dict()}
                return None

            try:
                while True:
                    try:
                        event = await wait_for_engine_event(event_iter.__anext__())
                    except StopAsyncIteration:
                        break
                    except TimeoutError as e:
                        raise StreamDisconnectedError(
                            f"Codex SDK stream idle timeout after {DEFAULT_EVENT_IDLE_TIMEOUT_SECONDS:.0f}s",
                            partial_text=_current_full_text(),
                            immediate_retry=True,
                        ) from e

                    method = events._event_method(event)
                    payload = events._event_payload(event)
                    if method in ("item/started", "item/updated", "item/completed"):
                        received_item = events._get_attr(payload, "item", None)
                        received_type = events._item_type(received_item)
                        if received_type in (
                            "command_execution",
                            "mcp_tool_call",
                            "file_change",
                            "web_search",
                            "dynamic_tool_call",
                            "collab_agent_tool_call",
                        ):
                            tool_evidence.started(
                                events._item_id(received_item),
                                events._codex_item_tool_name(received_item, received_type),
                            )
                    # A stop can race the final usage notification. Account
                    # for already-received usage before honoring interruption.
                    if method == "thread/tokenUsage/updated":
                        event_turn_id = events._get_str(payload, "turn_id", "turnId")
                        active_turn_id = events._get_str(turn, "id")
                        if event_turn_id and active_turn_id and event_turn_id != active_turn_id:
                            continue
                        usage_chunk = _usage_from_raw(events._get_attr(payload, "token_usage", None))
                        if usage_chunk:
                            yield usage_chunk
                    elif method == "turn/completed":
                        usage_chunk = _usage_from_raw(
                            events._get_attr(payload, "usage", None) or events._get_attr(payload, "token_usage", None)
                        )
                        if usage_chunk:
                            yield usage_chunk

                    if self._check_interrupted():
                        logger.info("Codex SDK streaming interrupted")
                        interrupted = True
                        end_chunk = _thinking_end_chunk()
                        if end_chunk:
                            yield end_chunk
                        interrupted_text = "[Session interrupted by user]"
                        yield {"type": "text_delta", "text": interrupted_text}
                        return

                    if method == "item/agentMessage/delta":
                        item_id = events._payload_item_id(payload)
                        delta = events._payload_delta(payload)
                        if delta:
                            agent_delta_seen.add(item_id)
                            _remember_agent_delta(item_id, delta)
                            yield {"type": "text_delta", "text": delta}
                        continue

                    if method in ("item/reasoning/textDelta", "item/reasoning/summaryTextDelta"):
                        item_id = events._payload_item_id(payload)
                        delta = events._payload_delta(payload)
                        if delta:
                            if item_id:
                                item_text_len[item_id] = item_text_len.get(item_id, 0) + len(delta)
                            for chunk in _thinking_delta_chunks(delta):
                                yield chunk
                        continue

                    if method == "item/plan/delta":
                        item_id = events._payload_item_id(payload)
                        delta = events._payload_delta(payload)
                        if delta:
                            if item_id:
                                item_text_len[item_id] = item_text_len.get(item_id, 0) + len(delta)
                            for chunk in _thinking_delta_chunks(delta):
                                yield chunk
                        continue

                    if method == "turn/plan/updated":
                        detail = events._format_plan_update(payload)
                        if detail:
                            for chunk in _thinking_delta_chunks(detail):
                                yield chunk
                        continue

                    if method == "item/commandExecution/outputDelta":
                        tool_id = events._payload_item_id(payload)
                        start = _tool_start_chunk(tool_id, "command")
                        if start:
                            yield start
                        detail = events._payload_delta(payload)
                        detail_chunk = _tool_detail_chunk(tool_id, "command", detail)
                        if detail_chunk:
                            yield detail_chunk
                        continue

                    if method in ("item/fileChange/outputDelta", "item/fileChange/patchUpdated"):
                        tool_id = events._payload_item_id(payload)
                        start = _tool_start_chunk(tool_id, "file_change")
                        if start:
                            yield start
                        detail = events._payload_delta(payload) or events._format_file_changes(
                            events._get_list(payload, "changes")
                        )
                        detail_chunk = _tool_detail_chunk(tool_id, "file_change", detail)
                        if detail_chunk:
                            yield detail_chunk
                        continue

                    if method == "item/mcpToolCall/progress":
                        tool_id = events._payload_item_id(payload)
                        start = _tool_start_chunk(tool_id, "mcp_tool")
                        if start:
                            yield start
                        detail_chunk = _tool_detail_chunk(tool_id, "mcp_tool", events._get_str(payload, "message"))
                        if detail_chunk:
                            yield detail_chunk
                        continue

                    if method in ("item/started", "item/updated"):
                        item = events._get_attr(payload, "item", None)
                        if item is None:
                            continue
                        item_type = events._item_type(item)
                        item_id = events._item_id(item)

                        if item_type == "agent_message":
                            text = events._extract_item_text(item)
                            if text:
                                prev_len = item_text_len.get(item_id, 0)
                                if len(text) > prev_len:
                                    delta = text[prev_len:]
                                    item_text_len[item_id] = len(text)
                                    agent_delta_seen.add(item_id)
                                    _remember_agent_delta(item_id, delta)
                                    yield {"type": "text_delta", "text": delta}

                        elif item_type in ("reasoning", "plan"):
                            text = events._extract_item_text(item)
                            if text:
                                prev_len = item_text_len.get(item_id, 0)
                                if len(text) > prev_len:
                                    delta = text[prev_len:]
                                    item_text_len[item_id] = len(text)
                                    for chunk in _thinking_delta_chunks(delta):
                                        yield chunk

                        elif item_type in (
                            "command_execution",
                            "mcp_tool_call",
                            "file_change",
                            "web_search",
                            "dynamic_tool_call",
                            "collab_agent_tool_call",
                        ):
                            start = _tool_start_chunk(item_id, events._codex_item_tool_name(item, item_type))
                            if start:
                                yield start
                        continue

                    if method == "item/completed":
                        item = events._get_attr(payload, "item", None)
                        if item is None:
                            continue
                        item_type = events._item_type(item)
                        item_id = events._item_id(item)

                        if item_type == "agent_message":
                            text = events._extract_item_text(item)
                            if text:
                                if item_id in agent_delta_seen:
                                    _set_agent_text(item_id, text)
                                else:
                                    _set_agent_text(item_id, text)
                                    yield {"type": "text_delta", "text": text}
                                item_text_len[item_id] = len(text)
                            else:
                                logger.debug(
                                    "Codex item/completed agent_message with empty text: %s",
                                    repr(item)[:300],
                                )

                        elif item_type in ("reasoning", "plan"):
                            text = events._extract_item_text(item)
                            if text:
                                prev_len = item_text_len.get(item_id, 0)
                                if len(text) > prev_len:
                                    for chunk in _thinking_delta_chunks(text[prev_len:]):
                                        yield chunk
                                item_text_len[item_id] = len(text)

                        elif item_type in (
                            "command_execution",
                            "mcp_tool_call",
                            "file_change",
                            "web_search",
                            "dynamic_tool_call",
                            "collab_agent_tool_call",
                        ):
                            tool_name = events._codex_item_tool_name(item, item_type)
                            start = _tool_start_chunk(item_id, tool_name)
                            if start:
                                yield start
                            if item_type == "file_change":
                                detail = events._format_file_changes(
                                    events._get_list(events._unwrap_thread_item(item), "changes")
                                )
                                detail_chunk = _tool_detail_chunk(item_id, tool_name, detail)
                                if detail_chunk:
                                    yield detail_chunk
                            if item_type == "command_execution":
                                unwrapped = events._unwrap_thread_item(item)
                                command = events._get_str(unwrapped, "command")
                                output = events._get_str(unwrapped, "aggregated_output", "aggregatedOutput")
                                exit_code = events._get_first_attr(unwrapped, "exit_code", "exitCode", default=None)
                                tool_evidence.record_tool_call(
                                    "Bash",
                                    {"command": command},
                                    item_id,
                                    output,
                                    is_error=exit_code is not None and exit_code != 0,
                                    extra_meta={"exit_code": exit_code} if exit_code is not None else None,
                                )
                            elif item_type == "file_change":
                                status = events._get_str(events._unwrap_thread_item(item), "status")
                                tool_evidence.record_tool_call(
                                    "Edit",
                                    {"file_path": detail},
                                    item_id,
                                    status or detail,
                                )
                            rec = events._item_to_tool_record(item)
                            if rec:
                                all_tool_records.append(rec)
                                tool_evidence.merge([rec])
                            if item_id not in tool_ended:
                                tool_ended.add(item_id)
                                yield {
                                    "type": "tool_end",
                                    "tool_id": item_id,
                                    "tool_name": tool_name,
                                }

                        else:
                            text = events._extract_item_text(item)
                            if text:
                                logger.info(
                                    "Codex item/completed type=%s has text (%d chars); emitting",
                                    item_type,
                                    len(text),
                                )
                                _set_agent_text(item_id, text)
                                yield {"type": "text_delta", "text": text}
                            else:
                                logger.debug(
                                    "Codex item/completed type=%s: %s",
                                    item_type,
                                    repr(item)[:300],
                                )
                        continue

                    if method == "thread/tokenUsage/updated":
                        continue

                    if method == "turn/completed":
                        completed_turn_count += 1
                        turn_result = events._wrap_result_message(payload, thread, completed_turns=completed_turn_count)
                        saved_tid = events._get_thread_id(thread)
                        if saved_tid and persist_thread:
                            _save_thread_id(self._anima_dir, saved_tid, session_type, chat_thread_id)
                        turn_obj = events._get_attr(payload, "turn", None)
                        error_obj = events._get_attr(turn_obj, "error", None)
                        error_msg = events._get_str(error_obj, "message")
                        if error_msg:
                            logger.error("Codex turn/completed error: %s", error_msg)
                            end_chunk = _thinking_end_chunk()
                            if end_chunk:
                                yield end_chunk
                            yield {
                                "type": "error",
                                "message": f"[Codex turn failed: {error_msg}]",
                                **events._codex_error_metadata(error_msg, self._model_config.model),
                            }
                        continue

                    if method == "turn/failed":
                        err_obj = events._get_attr(payload, "error", None)
                        error_msg = events._get_str(err_obj, "message") or str(err_obj or "")
                        logger.error("Codex turn.failed: %s", error_msg)
                        end_chunk = _thinking_end_chunk()
                        if end_chunk:
                            yield end_chunk
                        yield {
                            "type": "error",
                            "message": f"[Codex turn failed: {error_msg}]",
                            **events._codex_error_metadata(error_msg, self._model_config.model),
                        }
                        continue

                    if method == "error":
                        error_msg = events._get_str(payload, "message") or str(payload)
                        logger.error("Codex error event: %s", error_msg)
                        end_chunk = _thinking_end_chunk()
                        if end_chunk:
                            yield end_chunk
                        yield {
                            "type": "error",
                            "message": f"[Codex error: {error_msg}]",
                            **events._codex_error_metadata(error_msg, self._model_config.model),
                        }
                        continue

                    if method in ("thread/started", "turn/started"):
                        logger.debug("Codex lifecycle event: %s", method)
                        continue

                    logger.debug(
                        "Codex unhandled event method=%s attrs=%s",
                        method,
                        [a for a in dir(payload) if not a.startswith("_")][:15],
                    )
            finally:
                aclose = getattr(stream, "aclose", None)
                if callable(aclose):
                    await aclose()

        try:
            # Try resume first, fallback to fresh thread.
            fell_back = False
            if codex_thread_id:
                try:
                    gen = _stream_turn(codex_thread_id)
                    first_event: dict[str, Any] | None = None
                    try:
                        first_event = await asyncio.wait_for(
                            gen.__anext__(),
                            timeout=RESUME_TIMEOUT_SEC,
                        )
                    except (TimeoutError, StopAsyncIteration) as e:
                        if tool_evidence:
                            raise StreamDisconnectedError(
                                "Codex resumed stream ended after starting a tool",
                                partial_text=_current_full_text(),
                            ) from e
                        logger.warning(
                            "Codex resume timed out or empty (thread=%s), falling back to fresh thread.",
                            codex_thread_id,
                        )
                        if persist_thread:
                            _clear_thread_id(self._anima_dir, session_type, chat_thread_id)
                        fell_back = True
                        await gen.aclose()
                    except Exception as e:
                        if tool_evidence:
                            raise
                        logger.warning(
                            "Codex resume stream failed (thread=%s): %s",
                            codex_thread_id,
                            e,
                        )
                        if persist_thread:
                            _clear_thread_id(self._anima_dir, session_type, chat_thread_id)
                        fell_back = True
                        await gen.aclose()
                    else:
                        if first_event:
                            yield first_event
                        async for ev in gen:
                            yield ev
                except Exception as e:
                    if tool_evidence:
                        raise
                    logger.warning(
                        "Codex stream resume error: %s. Fresh thread.",
                        e,
                    )
                    if persist_thread:
                        _clear_thread_id(self._anima_dir, session_type, chat_thread_id)
                    fell_back = True
            else:
                fell_back = True

            if fell_back:
                try:
                    async for ev in _stream_turn(None):
                        yield ev
                except Exception as e:
                    if not tool_evidence and _should_cli_exec_fallback(e):
                        logger.warning("Codex SDK streaming failed; falling back to `codex exec`")
                        end_chunk = _thinking_end_chunk()
                        if end_chunk:
                            yield end_chunk
                        async for ev in self._execute_streaming_via_cli_exec(
                            system_prompt, prompt, tracker, trigger=trigger
                        ):
                            tool_evidence.observe(ev)
                            if ev.get("type") == "usage":
                                usage_acc.merge(events._token_usage(ev.get("usage") or {}))
                            elif ev.get("type") == "done":
                                # Native requests before transport fallback
                                # were also billed. Keep every result surface
                                # consistent with the already-emitted deltas.
                                if not ev.get("usage_already_emitted"):
                                    delta = events._token_usage(ev.get("usage") or {})
                                    usage_acc.merge(delta)
                                    if any(delta.to_dict().values()):
                                        yield {"type": "usage", "usage": delta.to_dict()}
                                ev = {**ev, "usage": usage_acc.to_dict(), "usage_already_emitted": True}
                                if ev.get("result_message") is not None:
                                    ev["result_message"].usage = usage_acc.to_dict()
                            yield ev
                        return
                    logger.exception("Codex SDK streaming error")
                    partial = _current_full_text()
                    is_buffer_overflow = _is_limit_overrun(e)
                    end_chunk = _thinking_end_chunk()
                    if end_chunk:
                        yield end_chunk
                    raise StreamDisconnectedError(
                        f"Codex SDK stream error: {e}",
                        partial_text=partial,
                        immediate_retry=is_buffer_overflow,
                    ) from e

            full_text = _current_full_text()
            if interrupted and not full_text:
                full_text = "[Session interrupted by user]"
            if not full_text and all_tool_records:
                full_text = events._synthesise_fallback(all_tool_records)
            if turn_result is None and (full_text or all_tool_records):
                turn_result = events.CodexResultMessage(
                    num_turns=max(1, completed_turn_count),
                    session_id=events._get_thread_id(active_thread) or "",
                    usage=usage_acc.to_dict(),
                )
            elif turn_result is not None:
                turn_result.usage = usage_acc.to_dict()

            replied_to = self._read_replied_to_file()
            end_chunk = _thinking_end_chunk()
            if end_chunk:
                yield end_chunk
            yield {
                "type": "done",
                "full_text": full_text,
                "result_message": turn_result,
                "replied_to_from_transcript": replied_to,
                "tool_call_records": tool_evidence.to_dicts(),
                "usage": usage_acc.to_dict(),
                "usage_already_emitted": True,
                "stop_kind": "interrupted" if interrupted else "normal",
            }
        except BaseException as exc:
            if isinstance(exc, (Exception, asyncio.CancelledError)):
                exc.usage = usage_acc.to_dict()
                exc.usage_already_emitted = True
                tool_evidence.merge(getattr(exc, "tool_call_records", None) or [])
                exc.tool_call_records = tool_evidence.to_dicts()
            raise
        finally:
            await setup._close_codex_client(codex)
