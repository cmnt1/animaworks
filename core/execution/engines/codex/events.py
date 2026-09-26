from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Codex SDK/CLI event conversion into AnimaWorks execution streams."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from core.execution.base import TokenUsage, ToolCallRecord, _truncate_for_record
from core.execution.error_classifier import (
    FailoverReason,
    classify_llm_error_message,
    guard_key,
    provider_family_of,
)
from core.execution.process_runner import ProcessRunner
from core.execution.rate_guard import get_rate_guard
from core.execution.tool_evidence import ToolEvidence
from core.prompt.context import ContextTracker

from . import setup

logger = logging.getLogger("animaworks.execution.codex_sdk")


def _get_thread_id(thread: Any) -> str | None:
    """Safely extract the thread ID from a Codex Thread object."""
    for attr in ("id", "thread_id"):
        val = getattr(thread, attr, None)
        if val:
            return str(val)
    return None


def _codex_error_metadata(message: str, model: str) -> dict[str, Any]:
    """Classify a Codex event error, report fleet blocks, and return chunk metadata."""
    reason, hint = classify_llm_error_message(message)
    if reason in {
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.QUOTA_EXHAUSTED,
    }:
        try:
            guard = get_rate_guard()
            cfg = guard.config
            block_seconds = (
                cfg.quota_block_seconds if reason is FailoverReason.QUOTA_EXHAUSTED else cfg.default_block_seconds
            )
            guard.report_block(
                guard_key(provider_family_of(model), "codex"),
                block_seconds,
                reason.value,
                reset_in_s=hint.reset_in_s,
            )
        except Exception:
            # Classification must not turn a provider error event into an
            # executor failure.  The shared guard remains fail-open.
            logger.debug("failed to report Codex error to rate guard", exc_info=True)

    if hint.is_terminal or not hint.retryable:
        return {"terminal": True, "reason": reason.value}
    return {}


_ITEM_TYPE_ALIASES = {
    "agentMessage": "agent_message",
    "commandExecution": "command_execution",
    "mcpToolCall": "mcp_tool_call",
    "fileChange": "file_change",
    "webSearch": "web_search",
    "dynamicToolCall": "dynamic_tool_call",
    "collabAgentToolCall": "collab_agent_tool_call",
}


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Return an attribute/key from SDK models, dicts, and lightweight test objects."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_first_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = _get_attr(obj, name, default)
        if value is not default:
            return value
    return default


def _get_str(obj: Any, *names: str) -> str:
    for name in names:
        value = _get_attr(obj, name, None)
        if isinstance(value, str):
            return value
    return ""


def _get_list(obj: Any, *names: str) -> list[Any]:
    for name in names:
        value = _get_attr(obj, name, None)
        if isinstance(value, list):
            return value
    return []


def _unwrap_thread_item(item: Any) -> Any:
    """Unwrap new SDK ``ThreadItem`` RootModel values while tolerating mocks."""
    root = _get_attr(item, "root", None)
    if root is not None and (_get_str(root, "type") or _get_str(root, "id")):
        return root
    return item


def _normalise_item_type(item_type: str) -> str:
    if not item_type:
        return ""
    return _ITEM_TYPE_ALIASES.get(item_type, item_type)


def _item_type(item: Any) -> str:
    return _normalise_item_type(_get_str(_unwrap_thread_item(item), "type"))


def _item_id(item: Any) -> str:
    return _get_str(_unwrap_thread_item(item), "id")


def _event_method(event: Any) -> str:
    """Return the Codex notification method, normalising old dotted test events."""
    method = _get_str(event, "method")
    if method:
        return method
    etype = _get_str(event, "type")
    if "." in etype:
        return etype.replace(".", "/")
    return etype


def _payload_looks_real(payload: Any) -> bool:
    if payload is None:
        return False
    if _get_str(payload, "thread_id", "threadId", "turn_id", "turnId", "item_id", "itemId"):
        return True
    if _get_str(payload, "delta", "message"):
        return True
    item = _get_attr(payload, "item", None)
    if item is not None and _item_type(item):
        return True
    turn = _get_attr(payload, "turn", None)
    return bool(turn is not None and _get_str(turn, "id"))


def _event_payload(event: Any) -> Any:
    payload = _get_attr(event, "payload", None)
    if _payload_looks_real(payload):
        return payload
    return event


def _payload_item_id(payload: Any) -> str:
    return _get_str(payload, "item_id", "itemId")


def _payload_delta(payload: Any) -> str:
    return _get_str(payload, "delta")


def _extract_item_text(item: Any) -> str:
    """Extract text content from a Codex completed item."""
    item = _unwrap_thread_item(item)
    content = _get_attr(item, "content", None)
    if content is not None:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                part_text = _get_str(part, "text")
                if part_text:
                    parts.append(part_text)
                elif isinstance(part, str):
                    parts.append(part)
            return "".join(parts)
    text = _get_str(item, "text")
    if text:
        return text
    summary = _get_list(item, "summary")
    if summary:
        return "".join(str(part) for part in summary)
    return ""


def _codex_item_tool_name(item: Any, item_type: str) -> str:
    """Derive a human-readable tool name from a Codex item."""
    item = _unwrap_thread_item(item)
    item_type = _normalise_item_type(item_type)
    if item_type == "mcp_tool_call":
        server = _get_str(item, "server")
        tool = _get_str(item, "tool")
        return f"{server}/{tool}" if server else tool or "mcp_tool"
    if item_type == "command_execution":
        cmd = _get_str(item, "command")
        return cmd[:60] if cmd else "command"
    if item_type == "file_change":
        return "file_change"
    if item_type == "web_search":
        query = _get_str(item, "query")
        return f"web_search: {query[:48]}" if query else "web_search"
    return _get_str(item, "name") or item_type or "unknown"


def _item_to_tool_record(item: Any) -> ToolCallRecord | None:
    """Convert a Codex item (command_execution / mcp_tool_call) to a ``ToolCallRecord``."""
    try:
        item = _unwrap_thread_item(item)
        item_type = _item_type(item)
        tool_id = _item_id(item)
        if item_type == "mcp_tool_call":
            name = _codex_item_tool_name(item, item_type)
            input_data = _get_attr(item, "arguments", {})
            result_obj = _get_attr(item, "result", None)
            result_data = str(_get_attr(result_obj, "content", "")) if result_obj else ""
            error_obj = _get_attr(item, "error", None)
            is_error = error_obj is not None
            return ToolCallRecord(
                tool_name=name,
                tool_id=tool_id,
                input_summary=_truncate_for_record(str(input_data), 500),
                result_summary=_truncate_for_record(result_data, 500),
                is_error=is_error,
            )
        if item_type == "command_execution":
            cmd = _get_str(item, "command")
            output = _get_str(item, "aggregated_output", "aggregatedOutput")
            exit_code = _get_first_attr(item, "exit_code", "exitCode", default=None)
            is_error = exit_code is not None and exit_code != 0
            return ToolCallRecord(
                tool_name=cmd[:80] if cmd else "command",
                tool_id=tool_id,
                input_summary=_truncate_for_record(cmd, 500),
                result_summary=_truncate_for_record(output, 500),
                is_error=is_error,
            )
        if item_type == "file_change":
            changes = _get_list(item, "changes")
            detail = _format_file_changes(changes)
            return ToolCallRecord(
                tool_name="file_change",
                tool_id=tool_id,
                input_summary=_truncate_for_record(detail, 500),
                result_summary=_truncate_for_record(_get_str(item, "status") or detail, 500),
                is_error=False,
            )
        # Legacy fallback for unknown tool-like items
        name = _get_str(item, "name") or "unknown"
        input_data = _get_attr(item, "input", {})
        result_data = _get_attr(item, "output", "")
        return ToolCallRecord(
            tool_name=name,
            tool_id=tool_id,
            input_summary=_truncate_for_record(str(input_data), 500),
            result_summary=_truncate_for_record(str(result_data), 500),
        )
    except Exception:
        return None


def _extract_tool_records(items: list[Any]) -> list[ToolCallRecord]:
    records: list[ToolCallRecord] = []
    for item in items:
        itype = _item_type(item)
        if itype in ("tool_use", "command_execution", "mcp_tool_call", "file_change"):
            rec = _item_to_tool_record(item)
            if rec:
                records.append(rec)
    return records


def _synthesise_fallback(tool_records: list[ToolCallRecord]) -> str:
    """Build a short fallback text when the model produced no text output."""
    names = [r.tool_name for r in tool_records[:5]]
    suffix = ", …" if len(tool_records) > 5 else ""
    fallback = f"(completed {len(tool_records)} tool call(s): {', '.join(names)}{suffix})"
    logger.warning(
        "Codex SDK produced no text output; synthesised fallback (tools=%d)",
        len(tool_records),
    )
    return fallback


def _usage_to_dict(usage: Any) -> dict[str, int]:
    """Normalise a Codex usage object (or dict) to a plain dict."""
    if isinstance(usage, dict):
        result: dict[str, int] = {}
        key_aliases = {
            "input_tokens": ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens"),
            "output_tokens": ("output_tokens", "outputTokens", "completion_tokens", "completionTokens"),
            "cached_input_tokens": ("cached_input_tokens", "cachedInputTokens", "cache_read_tokens"),
            "cache_write_input_tokens": ("cache_write_input_tokens", "cacheWriteInputTokens", "cache_write_tokens"),
            "reasoning_output_tokens": ("reasoning_output_tokens", "reasoningOutputTokens"),
            "total_tokens": ("total_tokens", "totalTokens"),
        }
        for out_key, aliases in key_aliases.items():
            for alias in aliases:
                val = usage.get(alias)
                if val is not None:
                    result[out_key] = int(val)
                    break
        return result or usage
    total_usage = _get_attr(usage, "total", None)
    if total_usage is not None and any(
        isinstance(_get_attr(total_usage, key, None), int)
        for key in ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens")
    ):
        usage = total_usage
    d: dict[str, int] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ):
        val = getattr(usage, key, None)
        if val is not None:
            d[key] = int(val)
    return d


def _token_usage(usage: Any) -> TokenUsage:
    """Codex input includes cached tokens; retain that convention explicitly."""
    raw = _usage_to_dict(usage)
    return TokenUsage(
        input_tokens=raw.get("input_tokens", 0) or raw.get("prompt_tokens", 0),
        output_tokens=raw.get("output_tokens", 0) or raw.get("completion_tokens", 0),
        cache_read_tokens=raw.get("cached_input_tokens", 0),
        cache_write_tokens=raw.get("cache_write_input_tokens", 0),
    )


class _CodexUsageAccumulator:
    """Turn-local deltas from thread totals, including resumed/reset counters.

    The first notification of a resumed thread can include months of usage.
    Its ``last`` is the first observed request of this turn, not the whole
    turn. Later monotonic totals supply deltas (also recovering omitted
    intermediate notifications); counter resets use the new request's last.
    Repeated snapshots are ignored. A fresh thread has a known zero baseline.
    """

    def __init__(self, *, fresh_thread: bool = False) -> None:
        self._fresh_thread = fresh_thread
        self._previous: dict[str, int] | None = None

    def update(self, raw: Any) -> TokenUsage:
        total_raw = _get_attr(raw, "total", None)
        last_raw = _get_attr(raw, "last", None)
        # Flat usage is already scoped to a turn (CLI/older SDK events).
        structured = total_raw is not None
        total = _token_usage(total_raw if structured else raw).to_dict()
        previous = self._previous
        if total == previous:
            return TokenUsage()
        self._previous = total
        if previous is None:
            if structured and not self._fresh_thread:
                if last_raw is None:
                    logger.warning("Codex resumed usage has no request breakdown; cumulative total not charged")
                    return TokenUsage()
                return _token_usage(last_raw)
            return TokenUsage(**total)
        if all(total[key] >= previous[key] for key in total):
            return TokenUsage(**{key: total[key] - previous[key] for key in total})
        # Ordered notifications can restart a counter epoch. Do not retain
        # historic fingerprints: the new epoch can repeat an earlier total.
        return _token_usage(last_raw) if last_raw is not None else TokenUsage(**total)


def _format_file_changes(changes: list[Any]) -> str:
    parts: list[str] = []
    for change in changes:
        kind = _get_attr(change, "kind", "")
        kind_text = getattr(kind, "value", kind)
        path = _get_str(change, "path")
        if kind_text or path:
            parts.append(f"{kind_text}: {path}".strip(": "))
    return "; ".join(parts[:10])


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _format_plan_update(payload: Any) -> str:
    """Format Codex plan updates for the existing GUI thinking channel."""
    lines: list[str] = []
    explanation = _get_str(payload, "explanation").strip()
    if explanation:
        lines.append(explanation)

    for step in _get_list(payload, "plan")[:10]:
        step_text = _get_str(step, "step", "text").strip()
        if not step_text:
            continue
        status_text = _enum_text(_get_attr(step, "status", "")).strip()
        if status_text:
            lines.append(f"[{status_text}] {step_text}")
        else:
            lines.append(step_text)

    return "\n".join(lines)


def _cli_exec_result_text(result: Any) -> str:
    """Extract text from a Codex CLI exec result payload."""
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
            if parts:
                return "".join(parts)
        if "text" in result:
            return str(result.get("text", ""))
    if isinstance(result, str):
        return result
    return ""


def _cli_exec_item_to_tool_record(item: dict[str, Any]) -> ToolCallRecord | None:
    """Convert a JSON event item from `codex exec --json` into a ToolCallRecord."""
    try:
        item_type = str(item.get("type", ""))
        tool_id = str(item.get("id", ""))
        if item_type == "mcp_tool_call":
            server = str(item.get("server", ""))
            tool = str(item.get("tool", ""))
            name = f"{server}/{tool}" if server else tool or "mcp_tool"
            result_text = _cli_exec_result_text(item.get("result"))
            return ToolCallRecord(
                tool_name=name,
                tool_id=tool_id,
                input_summary=_truncate_for_record(str(item.get("arguments", {})), 500),
                result_summary=_truncate_for_record(result_text, 500),
                is_error=item.get("error") is not None,
            )
        if item_type == "command_execution":
            cmd = str(item.get("command", ""))
            output = str(item.get("aggregated_output", "") or item.get("output", ""))
            exit_code = item.get("exit_code")
            is_error = exit_code is not None and exit_code != 0
            return ToolCallRecord(
                tool_name=cmd[:80] if cmd else "command",
                tool_id=tool_id,
                input_summary=_truncate_for_record(cmd, 500),
                result_summary=_truncate_for_record(output, 500),
                is_error=is_error,
            )
    except Exception:
        return None
    return None


@dataclass
class CodexResultMessage:
    """Adapter providing the ``num_turns`` / ``session_id`` interface
    expected by ``AgentCore`` session-chaining logic."""

    num_turns: int = 0
    session_id: str = ""
    usage: dict[str, int] | None = None


def _wrap_result_message(
    turn: Any,
    thread: Any | None = None,
    completed_turns: int = 0,
) -> CodexResultMessage:
    """Wrap a Codex turn/event into a ``CodexResultMessage``."""
    usage_raw = getattr(turn, "usage", None)
    usage = _usage_to_dict(usage_raw) if usage_raw else None
    raw_num_turns = getattr(turn, "num_turns", 0)
    try:
        num_turns = int(raw_num_turns or 0)
    except (TypeError, ValueError):
        num_turns = 0
    num_turns = num_turns or completed_turns
    if num_turns <= 0 and turn is not None:
        num_turns = 1
    session_id = ""
    if thread:
        session_id = _get_thread_id(thread) or ""
    return CodexResultMessage(
        num_turns=num_turns,
        session_id=session_id,
        usage=usage,
    )


class CodexEventsMixin(setup.CodexSetupMixin):
    async def _execute_streaming_via_cli_exec(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
        trigger: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Fallback executor using `codex exec --json` when the SDK transport is unstable."""
        self._write_codex_config(system_prompt)
        cmd = self._build_cli_exec_command()
        env = self._build_env()
        process_runner = ProcessRunner(drain_stderr=False)
        proc = await process_runner.start(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            limit=setup._SUBPROCESS_STREAM_LIMIT,
        )
        if proc.stdin is None or proc.stdout is None:
            await process_runner.close()
            setup._close_subprocess_stdio(proc)
            raise RuntimeError("Codex CLI exec fallback missing stdin/stdout")

        stderr_chunks: list[bytes] = []

        async def _read_stderr() -> None:
            if proc.stderr is None:
                return
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    break
                stderr_chunks.append(chunk)

        stderr_task = asyncio.create_task(_read_stderr())
        response_parts: list[str] = []
        tool_records: list[ToolCallRecord] = []
        tool_evidence = ToolEvidence(self._anima_dir)
        usage_acc = TokenUsage()
        emitted_tool_starts: set[str] = set()
        usage_meter = _CodexUsageAccumulator(fresh_thread=True)
        completed_turn_count = 0
        turn_completed = False
        thread_id = ""
        usage_dict: dict[str, int] | None = None

        try:
            proc.stdin.write(prompt.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

            while True:
                line = await self.read_line(proc.stdout)
                if not line:
                    break
                payload = self.parse_json_line(line)
                if payload is None:
                    continue

                ptype = str(payload.get("type", ""))
                if ptype == "thread.started":
                    thread_id = str(payload.get("thread_id", ""))
                    continue
                if ptype in ("turn.started",):
                    # CLI usage is turn-local, unlike native thread totals.
                    usage_meter = _CodexUsageAccumulator(fresh_thread=True)
                    turn_completed = False
                    continue

                if ptype == "item.started":
                    item = payload.get("item") or {}
                    item_type = str(item.get("type", ""))
                    item_id = str(item.get("id", ""))
                    if (
                        item_type in ("command_execution", "mcp_tool_call", "file_change")
                        and item_id not in emitted_tool_starts
                    ):
                        emitted_tool_starts.add(item_id)
                        tool_evidence.started(item_id, _codex_item_tool_name(item, item_type))
                        yield {
                            "type": "tool_start",
                            "tool_name": _codex_item_tool_name(type("Obj", (), item)(), item_type),
                            "tool_id": item_id,
                        }
                    continue

                if ptype == "item.completed":
                    item = payload.get("item") or {}
                    item_type = str(item.get("type", ""))
                    item_id = str(item.get("id", ""))

                    if item_type == "agent_message":
                        text = str(item.get("text", ""))
                        if text:
                            response_parts.append(text)
                            yield {"type": "text_delta", "text": text}
                        continue

                    if item_type in ("command_execution", "mcp_tool_call", "file_change"):
                        tool_evidence.started(item_id, _codex_item_tool_name(item, item_type))
                        if item_id not in emitted_tool_starts:
                            emitted_tool_starts.add(item_id)
                            yield {
                                "type": "tool_start",
                                "tool_name": _codex_item_tool_name(type("Obj", (), item)(), item_type),
                                "tool_id": item_id,
                            }
                        if item_type == "command_execution":
                            command = str(item.get("command", ""))
                            output = str(item.get("aggregated_output") or item.get("output", ""))
                            exit_code = item.get("exit_code")
                            tool_evidence.record_tool_call(
                                "Bash",
                                {"command": command},
                                item_id,
                                output,
                                is_error=exit_code is not None and exit_code != 0,
                                extra_meta={"exit_code": exit_code} if exit_code is not None else None,
                            )
                        elif item_type == "file_change":
                            detail = _format_file_changes(item.get("changes") or [])
                            tool_evidence.record_tool_call(
                                "Edit",
                                {"file_path": detail},
                                item_id,
                                item.get("status", "") or detail,
                            )
                        rec = _cli_exec_item_to_tool_record(item) or _item_to_tool_record(item)
                        if rec:
                            tool_records.append(rec)
                            tool_evidence.merge([rec])
                        yield {
                            "type": "tool_end",
                            "tool_name": _codex_item_tool_name(type("Obj", (), item)(), item_type),
                            "tool_id": item_id,
                        }
                        continue

                if ptype == "turn.completed":
                    if not turn_completed:
                        completed_turn_count += 1
                        turn_completed = True
                    usage_dict = _usage_to_dict(payload.get("usage", {}))
                    delta = usage_meter.update(usage_dict)
                    usage_acc.merge(delta)
                    if any(delta.to_dict().values()):
                        yield {"type": "usage", "usage": delta.to_dict()}
                    continue

            returncode = await proc.wait()
            await process_runner.close()
            await stderr_task
            stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
            if returncode != 0:
                raise RuntimeError(stderr_text or f"codex exec exited with code {returncode}")
            if stderr_text:
                logger.debug("Codex CLI exec stderr: %s", stderr_text[:500])
        except BaseException as exc:
            if isinstance(exc, (Exception, asyncio.CancelledError)):
                exc.usage = usage_acc.to_dict()
                exc.usage_already_emitted = True
                exc.tool_call_records = tool_evidence.to_dicts()
            raise
        finally:
            await process_runner.close()
            stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)
            setup._close_subprocess_stdio(proc)

        full_text = "\n".join(response_parts)
        if not full_text and tool_records:
            full_text = _synthesise_fallback(tool_records)
        replied_to = self._read_replied_to_file()
        yield {
            "type": "done",
            "full_text": full_text,
            "result_message": CodexResultMessage(
                num_turns=completed_turn_count or int(bool(full_text or tool_records)),
                session_id=thread_id,
                usage=usage_acc.to_dict(),
            ),
            "replied_to_from_transcript": replied_to,
            "tool_call_records": tool_evidence.to_dicts(),
            "usage": usage_acc.to_dict(),
            "usage_already_emitted": True,
        }
