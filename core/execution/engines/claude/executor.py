from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Mode S executor: Claude Agent SDK.

Runs Claude as a fully autonomous agent with Read/Write/Edit/Bash/Grep/Glob
tools via the Agent SDK subprocess.  Supports both blocking and streaming
execution.  Tool results are captured from UserMessage ToolResultBlock
instead of PostToolUse hooks.

Implementation is split across submodules for readability:
  - ``_sdk_security``: Security checks and output size guards
  - ``_sdk_session``: Session persistence, SDK input helpers, cleanup
  - ``_sdk_stream``: Tool logging/sanitization, stream block processing
  - ``_sdk_hooks``: PreToolUse/PreCompact hooks, subordinate management
  - ``_sdk_options``: SDK option building (Mixin)
  - ``_sdk_interrupt``: Graceful interrupt helpers
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import psutil

if TYPE_CHECKING:
    try:
        from claude_agent_sdk import ClaudeSDKClient
    except ImportError:
        pass

from pathlib import Path

# ── Re-exports from submodules (backward compatibility) ──────
from core.execution.base import BaseExecutor, ExecutionResult, StreamDisconnectedError, TokenUsage, ToolCallRecord
from core.execution.engines.claude import _sdk_session
from core.execution.engines.claude._sdk_options import SDKOptionsMixin
from core.execution.engines.claude._sdk_session import (
    _RESUMABLE_SESSION_TYPES,
    COMPACT_TIMEOUT_SEC,
    RESUME_TIMEOUT_SEC,
    _build_sdk_query_input,  # noqa: F401 - backward-compatible re-export
    _cleanup_prompt_files,
    _cleanup_tool_outputs,
    _load_session_id,
    _resolve_session_type,
    _save_session_id,  # noqa: F401 - backward-compatible re-export
    compact_sdk_session,
)
from core.execution.engines.claude._sdk_stream import (
    StreamingContext,
    StreamingState,
    _finalize_pending_records,
    _handle_tool_result_block,  # noqa: F401 - backward-compatible re-export
    _handle_tool_use_block,  # noqa: F401 - backward-compatible re-export
    _tool_result_content_len,  # noqa: F401 - backward-compatible re-export
    process_stream_messages,
)
from core.execution.events import done_event, error_event, stream_events
from core.execution.process_runner import ProcessRunner
from core.llm.guard.error_classifier import (
    classify_llm_error_message,
    detect_cli_error_envelope,
    guard_key,
    provider_family_of,
)
from core.llm.guard.rate_guard import get_rate_guard
from core.memory.conversation.shortterm import ShortTermMemory
from core.prompt.context import ContextTracker
from core.schemas import ImageData, ModelConfig
from core.text.tokens import estimate_tokens

logger = logging.getLogger("animaworks.execution.agent_sdk")

__all__ = ["AgentSDKExecutor", "StreamDisconnectedError"]


def _detect_sdk_auth_failure(text: str) -> str | None:
    """Return auth failure text when Claude Code surfaced a 401 auth error."""
    body = (text or "").strip()
    if not body:
        return None

    folded = body.casefold()
    auth_markers = (
        "failed to authenticate",
        "invalid authentication credentials",
        "authentication_error",
        "not authenticated",
    )
    if not any(marker in folded for marker in auth_markers):
        return None
    if not any(marker in folded for marker in ("401", "api error", "unauthorized", "auth")):
        return None
    return body


def _sdk_failure_text(result: Any, text: str, assistant_error: str | None = None) -> str | None:
    """Recognize SDK failure envelopes, not error words in normal answers."""
    result_text = getattr(result, "result", None)
    errors = getattr(result, "errors", None)
    details = [item for item in errors if isinstance(item, str)] if isinstance(errors, list) else []
    if isinstance(result_text, str) and result_text.strip():
        details.append(result_text.strip())
    subtype = getattr(result, "subtype", "")
    explicit_error = (
        getattr(result, "is_error", False) is True
        or (isinstance(subtype, str) and subtype.startswith("error_"))
        or bool(assistant_error)
    )
    if explicit_error:
        detail = "\n".join(details) or text.strip() or assistant_error or str(subtype) or "SDKError"
        error_status = {
            "authentication_failed": 401,
            "billing_error": 402,
            "rate_limit": 429,
            "invalid_request": 400,
            "server_error": 500,
        }.get(assistant_error or "")
        return f"API Error: {error_status} ({assistant_error})\n{detail}" if error_status else detail
    # Some Claude CLI transports omit is_error and print a synthetic API error
    # as assistant text. Restrict this compatibility path to their leading
    # envelope + known transport/status signature; prose mentioning an error
    # or a quoted log is still a successful model answer.
    return detect_cli_error_envelope(text)


def _usage_from_stream_event(value: Any) -> TokenUsage:
    """Convert streaming usage metadata to the blocking result type."""
    if not isinstance(value, dict):
        return TokenUsage()
    return TokenUsage(
        input_tokens=value.get("input_tokens", 0) or 0,
        output_tokens=value.get("output_tokens", 0) or 0,
        cache_read_tokens=value.get("cache_read_tokens", 0) or 0,
        cache_write_tokens=value.get("cache_write_tokens", 0) or 0,
    )


def _tool_records_from_stream_event(value: Any) -> list[ToolCallRecord]:
    """Convert serialized streaming tool records back to executor records."""
    if not isinstance(value, list):
        return []
    fields = ("tool_name", "tool_id", "input_summary", "result_summary", "is_error")
    records: list[ToolCallRecord] = []
    for item in value:
        if isinstance(item, ToolCallRecord):
            records.append(item)
        elif isinstance(item, dict):
            records.append(ToolCallRecord(**{key: item[key] for key in fields if key in item}))
    return records


# ── SDK subprocess PID tracking / cleanup ────────────


def _extract_sdk_pid(client: Any) -> int | None:
    """Return the Claude Agent SDK subprocess PID if available.

    Reads ``client._transport._process.pid`` defensively when the SDK
    wired a subprocess transport.

    Args:
        client: An active ``ClaudeSDKClient`` instance.

    Returns:
        Subprocess PID, or ``None`` when unavailable or invalid.
    """
    try:
        transport = getattr(client, "_transport", None)
        if transport is None:
            return None
        proc = getattr(transport, "_process", None)
        if proc is None:
            return None
        raw_pid = getattr(proc, "pid", None)
        if raw_pid is None:
            return None
        pid = int(raw_pid)
    except Exception:
        logger.debug("failed to extract SDK subprocess pid", exc_info=True)
        return None
    return pid if pid > 0 else None


def _kill_sdk_process(pid: int | None, create_time: float | None) -> None:
    """Best-effort terminate of a leaked SDK subprocess and its descendants.

    Verifies the PID still refers to the same OS process (when ``create_time``
    was recorded) and that the process name looks like Claude/node before
    sending signals. Never raises.

    Args:
        pid: Target PID from :func:`_extract_sdk_pid`, or ``None``.
        create_time: ``psutil.Process.create_time()`` captured while the client
            was connected, used to detect PID reuse; ``None`` skips this check.
    """
    if pid is None:
        return
    try:
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return

        if create_time is not None:
            try:
                actual_ct = float(proc.create_time())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return
            except Exception:
                logger.debug(
                    "SDK cleanup: cannot read create_time for pid=%s",
                    pid,
                    exc_info=True,
                )
                return
            if abs(actual_ct - create_time) > 2.0:
                logger.debug(
                    "SDK cleanup: skipping kill pid=%s (create_time mismatch, possible PID reuse)",
                    pid,
                )
                return

        try:
            name = (proc.name() or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        except Exception:
            logger.debug("SDK cleanup: cannot read name for pid=%s", pid, exc_info=True)
            return
        if "claude" not in name and "node" not in name:
            logger.debug(
                "SDK cleanup: skipping kill pid=%s (unexpected process name %r)",
                pid,
                name,
            )
            return

        ProcessRunner.terminate_process_tree_sync(pid)
        logger.info("terminated leaked Claude SDK subprocess tree (pid=%s)", pid)
    except Exception:
        logger.debug("SDK cleanup: unexpected error for pid=%s", pid, exc_info=True)


# ── AgentSDKExecutor ─────────────────────────────────────────


class AgentSDKExecutor(SDKOptionsMixin, BaseExecutor):
    """Execute via Claude Agent SDK (Mode S).

    The SDK spawns a subprocess where Claude has full tool access.
    Tool results are captured from UserMessage ToolResultBlock content
    via ``_handle_tool_result_block``.
    """

    session_engine = "agent_sdk"
    tracks_sdk_session_state = True

    def __init__(
        self,
        model_config: ModelConfig,
        anima_dir: Path,
        tool_registry: list[str] | None = None,
        personal_tools: dict[str, str] | None = None,
        interrupt_event: asyncio.Event | None = None,
    ) -> None:
        super().__init__(model_config, anima_dir, interrupt_event=interrupt_event)
        self._tool_registry = tool_registry or []
        self._personal_tools = personal_tools or {}
        self._active_client: ClaudeSDKClient | None = None

    @property
    def supports_streaming(self) -> bool:  # noqa: D102
        return True

    @property
    def supports_message_injection(self) -> bool:  # noqa: D102
        return True

    async def inject_message(self, message: str) -> bool:
        """Send an additional user turn to the active bidirectional SDK client."""
        client = self._active_client
        if client is None:
            return False
        await client.query(message)
        return True

    def _init_session_stats(
        self,
        system_prompt: str,
        prompt: str,
        trigger: str,
        *,
        task_compaction_count: int = 0,
    ) -> dict[str, Any]:
        """Build the mutable session-stats dict shared with PreToolUse hook."""
        is_task = trigger.startswith("task:")
        return {
            "tool_call_count": 0,
            "total_result_bytes": 0,
            "system_prompt_tokens": estimate_tokens(system_prompt),
            "user_prompt_tokens": estimate_tokens(prompt),
            "force_chain": False,
            "task_compact_requested": False,
            "task_compaction_tokens": self._model_config.task_compaction_tokens if is_task else 0,
            "task_compaction_count": task_compaction_count,
            "task_compaction_max": self._model_config.task_compaction_max if is_task else 0,
            "last_context_tokens": 0,
            "trigger": trigger,
            "start_time": time.monotonic(),
            "hb_soft_warned": False,
            "hb_soft_timeout": self._hb_soft_timeout_s,
        }

    def _should_retry_sdk_auth_failure(self) -> bool:
        """Return True when auth failures should trigger a fresh-session retry."""
        return (self._model_config.mode_s_auth or "max") == "max"

    def _rate_guard_preflight(self) -> None:
        """Log when this model's realm is rate-guarded (start-time suppression only).

        The SDK owns its internal retries, so a guarded realm does not defer the
        session — this is observability so a fleet-wide throttle is visible at
        session start.  Keyed on the Mode-S auth realm the SDK authenticates
        against (``max``/``api``/``bedrock``/``vertex``), which is independent of
        the API-key ``api`` realm used by LiteLLM.
        """
        family = provider_family_of(self._model_config.model)
        realm = self._model_config.mode_s_auth or "max"
        key = guard_key(family, realm)
        blocked = get_rate_guard().blocked_remaining(key)
        if blocked > 0:
            logger.info(
                "S session start: %s rate-guarded for %.0fs (continuing; SDK retries apply)",
                key,
                blocked,
            )

    # ── Blocking execution ───────────────────────────────────

    async def execute(
        self,
        prompt: str,
        system_prompt: str = "",
        tracker: ContextTracker | None = None,
        shortterm: ShortTermMemory | None = None,
        trigger: str = "",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        thread_id: str = "default",
    ) -> ExecutionResult:
        """Consume the streaming SDK path and adapt its terminal result."""
        if tracker is None:
            tracker = ContextTracker(
                model=self._model_config.model,
                threshold=self._model_config.context_threshold,
                absolute_ceiling=self._model_config.context_absolute_ceiling,
            )

        execution_snapshot: dict[str, Any] = {}
        try:
            terminal_event: dict[str, Any] | None = None
            async for event in self.execute_streaming(
                system_prompt=system_prompt,
                prompt=prompt,
                tracker=tracker,
                images=images,
                prior_messages=prior_messages,
                trigger=trigger,
                thread_id=thread_id,
                _execution_snapshot=execution_snapshot,
                _aggregate_result=True,
            ):
                if event.get("type") in {"done", "error"}:
                    terminal_event = event

        except Exception as exc:
            if not isinstance(exc, (StreamDisconnectedError, TimeoutError)):
                raise
            logger.exception("Agent SDK execution error")
            root_exc = exc
            while root_exc.__cause__ is not None:
                root_exc = root_exc.__cause__
            partial_text = getattr(exc, "partial_text", "") or execution_snapshot.get("response_text", "")
            if execution_snapshot.get("auth_retry_started"):
                return ExecutionResult(
                    text=f"[Agent SDK Error: {root_exc}]",
                    tool_call_records=[],
                    error=True,
                    usage=_usage_from_stream_event(execution_snapshot.get("usage")),
                )
            partial_records = _tool_records_from_stream_event(execution_snapshot.get("tool_call_records"))
            pending_records = {record.tool_id: record for record in partial_records}
            return ExecutionResult(
                text=f"[Agent SDK Error: {root_exc}]\n{partial_text}",
                tool_call_records=_finalize_pending_records(pending_records),
                error=True,
                usage=_usage_from_stream_event(execution_snapshot.get("usage")),
            )

        if terminal_event is None:
            partial_records = _tool_records_from_stream_event(execution_snapshot.get("tool_call_records"))
            pending_records = {record.tool_id: record for record in partial_records}
            return ExecutionResult(
                text=execution_snapshot.get("response_text") or "(no response)",
                result_message=execution_snapshot.get("result_message"),
                replied_to_from_transcript=self._read_replied_to_file(),
                tool_call_records=_finalize_pending_records(pending_records),
                force_chain=bool(execution_snapshot.get("force_chain", False)),
                task_compact_requested=bool(execution_snapshot.get("task_compact_requested", False)),
                usage=_usage_from_stream_event(execution_snapshot.get("usage")),
            )

        result_message = terminal_event.get("result_message")
        tool_records = _tool_records_from_stream_event(terminal_event.get("tool_call_records"))
        usage = _usage_from_stream_event(terminal_event.get("usage"))
        if terminal_event.get("type") == "error":
            if result_message is None:
                result_message = execution_snapshot.get("result_message")
            return ExecutionResult(
                text=terminal_event.get("message") or "(no response)",
                result_message=result_message,
                replied_to_from_transcript=self._read_replied_to_file(),
                tool_call_records=tool_records,
                force_chain=bool(execution_snapshot.get("force_chain", False)),
                task_compact_requested=bool(execution_snapshot.get("task_compact_requested", False)),
                usage=usage,
                error=True,
            )

        full_text = terminal_event.get("full_text") or "(no response)"
        if terminal_event.get("stop_kind") == "interrupted":
            completed_text = execution_snapshot.get("response_text", "")
            full_text = (
                f"{completed_text}\n[Session interrupted by user]"
                if completed_text
                else "[Session interrupted by user]"
            )
        replied_to = terminal_event.get("replied_to_from_transcript") or set()
        return ExecutionResult(
            text=full_text,
            result_message=result_message,
            replied_to_from_transcript=replied_to,
            tool_call_records=tool_records,
            force_chain=bool(terminal_event.get("force_chain", False)),
            task_compact_requested=bool(terminal_event.get("task_compact_requested", False)),
            usage=usage,
        )

    # ── Streaming execution ──────────────────────────────────

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
        task_compaction_count: int = 0,
        resume_session_id: str | None = None,
        _execution_snapshot: dict[str, Any] | None = None,
        _aggregate_result: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream events from Claude Agent SDK."""
        from claude_agent_sdk import ClaudeSDKClient, ClaudeSDKError, ProcessError

        self._rate_guard_preflight()
        _cw = self._resolve_cw()
        session_stats = self._init_session_stats(
            system_prompt,
            prompt,
            trigger,
            task_compaction_count=task_compaction_count,
        )
        session_type = _resolve_session_type(trigger)
        if resume_session_id:
            session_id_to_resume = resume_session_id
        elif session_type in _RESUMABLE_SESSION_TYPES:
            session_id_to_resume = _load_session_id(self._anima_dir, session_type, thread_id=thread_id)
        else:
            _sdk_session.clear_session_id_for_type(self._anima_dir, session_type, thread_id=thread_id)
            session_id_to_resume = None

        options, _temp_files = self._build_sdk_options(
            system_prompt,
            _cw,
            session_stats,
            resume=session_id_to_resume,
            include_partial_messages=True,
        )
        _prompt_files: list[Path] = list(_temp_files)
        state = StreamingState(usage_acc=TokenUsage())
        ctx = StreamingContext(
            prompt=prompt,
            images=images,
            session_stats=session_stats,
            tracker=tracker,
            session_type=session_type,
            model=self._model_config.model,
            anima_dir=self._anima_dir,
            cw_overrides=self._resolve_cw_overrides(),
            check_interrupted=self._check_interrupted,
            thread_id=thread_id,
        )
        emitted_text_delta = False

        last_result_message: Any = None

        def _snapshot_execution_state() -> None:
            nonlocal last_result_message
            if _execution_snapshot is None:
                return
            if (
                _aggregate_result
                and state.result_message is not None
                and state.result_message is not last_result_message
            ):
                tracker.update_from_result_message(getattr(state.result_message, "usage", None))
                last_result_message = state.result_message
            _execution_snapshot.update(
                response_text="\n".join(state.response_text),
                tool_call_records=[asdict(record) for record in state.pending_records.values()],
                usage=state.usage_acc.to_dict(),
                result_message=state.result_message,
                force_chain=session_stats.get("force_chain", False),
                task_compact_requested=session_stats.get("task_compact_requested", False),
                interrupted=state.interrupted,
            )

        _snapshot_execution_state()
        sdk_pid: int | None = None
        sdk_pid_create_time: float | None = None

        async def _fresh_session() -> AsyncGenerator[dict[str, Any], None]:
            nonlocal sdk_pid, sdk_pid_create_time
            fresh_opts, tfs = self._build_sdk_options(
                system_prompt,
                _cw,
                session_stats,
                resume=None,
                include_partial_messages=True,
            )
            _prompt_files.extend(tfs)
            try:
                async with ClaudeSDKClient(options=fresh_opts) as fc:
                    logger.info("ClaudeSDKClient connected (fresh session retry)")
                    self._active_client = fc
                    sdk_pid = _extract_sdk_pid(fc)
                    sdk_pid_create_time = None
                    if sdk_pid is not None:
                        try:
                            sdk_pid_create_time = float(psutil.Process(sdk_pid).create_time())
                        except Exception:
                            logger.debug(
                                "failed to read create_time for SDK subprocess pid=%s",
                                sdk_pid,
                                exc_info=True,
                            )
                    try:
                        async for ev in process_stream_messages(
                            fc,
                            ctx,
                            state,
                            flush_unterminated_messages=_aggregate_result,
                            update_context_tracker=not _aggregate_result,
                        ):
                            _snapshot_execution_state()
                            yield ev
                    finally:
                        _snapshot_execution_state()
                        if self._active_client is fc:
                            self._active_client = None
            except BaseException as exc:
                if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                    raise
                logger.exception("Agent SDK streaming error (fresh session retry)")
                raise StreamDisconnectedError(
                    f"Agent SDK stream error ({type(exc).__name__}): {exc}",
                    partial_text="\n".join(state.response_text),
                ) from exc

        async def _run_stream_options(run_options, *, resume_guard: bool) -> AsyncGenerator[dict[str, Any], None]:
            nonlocal emitted_text_delta, sdk_pid, sdk_pid_create_time
            async with ClaudeSDKClient(options=run_options) as client:
                logger.info("ClaudeSDKClient connected")
                self._active_client = client
                sdk_pid = _extract_sdk_pid(client)
                sdk_pid_create_time = None
                if sdk_pid is not None:
                    try:
                        sdk_pid_create_time = float(psutil.Process(sdk_pid).create_time())
                    except Exception:
                        logger.debug(
                            "failed to read create_time for SDK subprocess pid=%s",
                            sdk_pid,
                            exc_info=True,
                        )
                try:
                    gen = process_stream_messages(
                        client,
                        ctx,
                        state,
                        flush_unterminated_messages=_aggregate_result,
                        update_context_tracker=not _aggregate_result,
                    )
                    if resume_guard:
                        try:
                            first = await asyncio.wait_for(gen.__anext__(), timeout=RESUME_TIMEOUT_SEC)
                        except TimeoutError:
                            logger.warning("Resume timed out (session_id=%s)", session_id_to_resume)
                            await gen.aclose()
                            _sdk_session._clear_session_id(self._anima_dir, session_type, thread_id=thread_id)
                            raise
                        except StopAsyncIteration:
                            logger.warning("Resume stream empty (session_id=%s)", session_id_to_resume)
                            _sdk_session._clear_session_id(self._anima_dir, session_type, thread_id=thread_id)
                            raise
                        else:
                            if first.get("type") == "text_delta":
                                emitted_text_delta = True
                            _snapshot_execution_state()
                            yield first
                    async for ev in gen:
                        if ev.get("type") == "text_delta":
                            emitted_text_delta = True
                        _snapshot_execution_state()
                        yield ev
                finally:
                    _snapshot_execution_state()
                    if self._active_client is client:
                        self._active_client = None

        try:
            logger.info("ClaudeSDKClient connecting (streaming, resume=%s)", session_id_to_resume)
            if session_id_to_resume:
                fell_back = False
                try:
                    async for ev in _run_stream_options(options, resume_guard=True):
                        yield ev
                except (TimeoutError, StopAsyncIteration):
                    fell_back = True
                except (ProcessError, ClaudeSDKError) as e:
                    logger.warning("SDK resume failed (session_id=%s): %s", session_id_to_resume, e)
                    _sdk_session._clear_session_id(self._anima_dir, session_type, thread_id=thread_id)
                    fell_back = True
                except Exception as e:
                    if isinstance(e, (asyncio.CancelledError, GeneratorExit)):
                        raise
                    logger.warning(
                        "SDK resume failed with unexpected error (session_id=%s): %s", session_id_to_resume, e
                    )
                    _sdk_session._clear_session_id(self._anima_dir, session_type, thread_id=thread_id)
                    fell_back = True
                if fell_back:
                    if resume_session_id:
                        raise StreamDisconnectedError(
                            f"Task SDK session resume failed (session_id={resume_session_id})",
                            partial_text="\n".join(state.response_text),
                        )
                    async for ev in _fresh_session():
                        yield ev
            else:
                async for ev in _run_stream_options(options, resume_guard=False):
                    yield ev
            logger.debug("ClaudeSDKClient disconnected")
        except BaseException as e:
            if isinstance(e, (asyncio.CancelledError, GeneratorExit)):
                raise
            logger.exception("Agent SDK streaming error")
            raise StreamDisconnectedError(
                f"Agent SDK stream error ({type(e).__name__}): {e}",
                partial_text="\n".join(state.response_text),
            ) from e
        finally:
            _snapshot_execution_state()
            _kill_sdk_process(sdk_pid, sdk_pid_create_time)
            _cleanup_tool_outputs(self._anima_dir)
            _cleanup_prompt_files(_prompt_files)

        auth_failure = _detect_sdk_auth_failure(
            _sdk_failure_text(state.result_message, "\n".join(state.response_text), state.sdk_error) or ""
        )
        if (
            auth_failure
            and self._should_retry_sdk_auth_failure()
            and (not emitted_text_delta or _aggregate_result)
            and not resume_session_id
        ):
            logger.warning("Claude SDK returned auth failure text during streaming; retrying fresh session once")
            if session_type in _RESUMABLE_SESSION_TYPES:
                _sdk_session._clear_session_id(self._anima_dir, session_type, thread_id=thread_id)
            state = StreamingState(usage_acc=TokenUsage())
            if _execution_snapshot is not None:
                _execution_snapshot["auth_retry_started"] = True
            _snapshot_execution_state()
            ctx = StreamingContext(
                prompt=prompt,
                images=images,
                session_stats=session_stats,
                tracker=tracker,
                session_type=session_type,
                model=self._model_config.model,
                anima_dir=self._anima_dir,
                cw_overrides=self._resolve_cw_overrides(),
                check_interrupted=self._check_interrupted,
                thread_id=thread_id,
            )
            emitted_text_delta = False
            try:
                async for ev in _fresh_session():
                    if ev.get("type") == "text_delta":
                        emitted_text_delta = True
                    yield ev
            finally:
                _snapshot_execution_state()
                _kill_sdk_process(sdk_pid, sdk_pid_create_time)
                _cleanup_tool_outputs(self._anima_dir)
                _cleanup_prompt_files(_prompt_files)

        all_tool_records = _finalize_pending_records(state.pending_records)
        full_text = "\n".join(state.response_text) or "(no response)"
        failure = _sdk_failure_text(state.result_message, "\n".join(state.response_text), state.sdk_error)
        if failure and not state.interrupted:
            reason, _hint = classify_llm_error_message(failure)
            yield error_event(
                failure,
                terminal=True,
                reason=reason.value,
                usage=state.usage_acc.to_dict(),
                tool_call_records=[asdict(r) for r in all_tool_records],
            )
            return
        replied_to = self._read_replied_to_file()
        yield done_event(
            full_text,
            result_message=state.result_message,
            stop_kind="interrupted"
            if state.interrupted
            else "empty_response"
            if full_text == "(no response)"
            else "normal",
            replied_to_from_transcript=replied_to,
            tool_call_records=[asdict(r) for r in all_tool_records],
            force_chain=session_stats.get("force_chain", False),
            task_compact_requested=session_stats.get("task_compact_requested", False),
            session_id=getattr(state.result_message, "session_id", None),
            usage=state.usage_acc.to_dict(),
        )

    async def compact_session_by_id(
        self,
        session_id: str,
        *,
        system_prompt: str,
        trigger: str,
        summary_instructions: str,
    ) -> bool:
        """Compact an active task session while retaining its SDK configuration."""
        from claude_agent_sdk import ClaudeSDKClient

        if not session_id:
            return False

        prompt = f"/compact {summary_instructions}"
        session_stats = self._init_session_stats(system_prompt, prompt, trigger)
        # The compact command itself must not recursively request task compaction.
        session_stats["task_compaction_tokens"] = 0
        options, temp_files = self._build_sdk_options(
            system_prompt,
            self._resolve_cw(),
            session_stats,
            resume=session_id,
            include_partial_messages=True,
        )
        sdk_pid: int | None = None
        sdk_pid_create_time: float | None = None
        active_client: Any = None
        compacted = False
        try:
            async with asyncio.timeout(COMPACT_TIMEOUT_SEC):
                async with ClaudeSDKClient(options=options) as client:
                    active_client = client
                    self._active_client = client
                    sdk_pid = _extract_sdk_pid(client)
                    if sdk_pid is not None:
                        try:
                            sdk_pid_create_time = float(psutil.Process(sdk_pid).create_time())
                        except Exception:
                            logger.debug("failed to read create_time for SDK subprocess pid=%s", sdk_pid, exc_info=True)
                    await client.query(prompt)
                    async for message in client.receive_messages():
                        if type(message).__name__ == "ResultMessage":
                            compacted = bool(getattr(message, "session_id", None))
                            break
            logger.info(
                "Task SDK session compaction %s (session=%s, task_id=%s)",
                "completed" if compacted else "did not return a session id",
                session_id,
                trigger.removeprefix("task:"),
            )
            return compacted
        except Exception:
            logger.exception(
                "Task SDK session compaction failed (session=%s, task_id=%s)",
                session_id,
                trigger.removeprefix("task:"),
            )
            return False
        finally:
            if self._active_client is active_client:
                self._active_client = None
            _kill_sdk_process(sdk_pid, sdk_pid_create_time)
            _cleanup_prompt_files(temp_files)

    async def compact_session(
        self,
        anima_dir: Path,
        session_type: str = "chat",
        thread_id: str = "default",
    ) -> bool:
        """Delegate to ``compact_sdk_session`` for backward compatibility."""
        return await compact_sdk_session(anima_dir, session_type, thread_id)
