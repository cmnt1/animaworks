from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Monkey-patches for the claude-agent-sdk Python package.

Patch 1 — ``SubprocessCLITransport.close()`` (all platforms):
  Wait for the CLI subprocess to exit gracefully after stdin EOF (with a
  timeout) before sending SIGTERM, so the CLI can flush the session JSONL.

Patch 2 — ``Query.wait_for_result_and_end_input()`` (Windows only):
  Keep stdin open throughout the entire SDK session.  Without this, the
  SDK closes stdin immediately after sending the user message (because
  hooks and SDK-type MCP servers are disabled on Windows).  The Claude
  Code CLI interprets stdin EOF as a disconnect signal and may abort
  multi-turn tool execution, causing the session to freeze.

Upstream references:
  - https://github.com/anthropics/claude-agent-sdk-python/pull/614
  - https://github.com/anthropics/claude-code/issues/21971
"""

import inspect
import logging
import sys
from contextlib import suppress

logger = logging.getLogger("animaworks.execution.agent_sdk")

_GRACEFUL_EXIT_TIMEOUT_SEC = 5

_patched = False


class _NoopAsyncContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


async def _maybe_await(result: object) -> None:
    if inspect.isawaitable(result):
        await result


def _set_attr_safely(obj: object, name: str, value: object) -> None:
    with suppress(Exception):
        setattr(obj, name, value)


def _native_close_has_graceful_wait(close_fn: object) -> bool:
    """Return True when SDK close already waits before terminating the process."""
    try:
        source = inspect.getsource(inspect.unwrap(close_fn))
    except (OSError, TypeError):
        return False

    compact = "".join(source.split())
    has_bounded_wait = "fail_after" in source
    waits_for_process = "awaitself._process.wait()" in compact or "awaitprocess.wait()" in compact
    terminates_after_wait = ".terminate(" in source or "terminate()" in source
    return has_bounded_wait and waits_for_process and terminates_after_wait


def _patch_transport_close() -> None:
    """Patch ``SubprocessCLITransport.close()`` — graceful shutdown."""
    import anyio
    from claude_agent_sdk._internal.transport import subprocess_cli as subprocess_cli_module

    SubprocessCLITransport = subprocess_cli_module.SubprocessCLITransport
    if _native_close_has_graceful_wait(SubprocessCLITransport.close):
        logger.info("Skipping SubprocessCLITransport.close() patch; SDK close is already graceful")
        return

    active_children = getattr(subprocess_cli_module, "_ACTIVE_CHILDREN", None)

    async def _patched_close(self: SubprocessCLITransport) -> None:  # type: ignore[override]
        process = getattr(self, "_process", None)
        if not process:
            _set_attr_safely(self, "_ready", False)
            return

        # Close stderr task group if active
        stderr_task_group = getattr(self, "_stderr_task_group", None)
        if stderr_task_group:
            with suppress(Exception):
                cancel_scope = getattr(stderr_task_group, "cancel_scope", None)
                cancel = getattr(cancel_scope, "cancel", None)
                if callable(cancel):
                    cancel()
                aexit = getattr(stderr_task_group, "__aexit__", None)
                if callable(aexit):
                    await aexit(None, None, None)
            _set_attr_safely(self, "_stderr_task_group", None)

        # Newer SDKs use a single stderr task instead of a task group.
        stderr_task = getattr(self, "_stderr_task", None)
        if stderr_task is not None:
            should_cancel = True
            done = getattr(stderr_task, "done", None)
            if callable(done):
                with suppress(Exception):
                    should_cancel = not done()
            if should_cancel:
                cancel = getattr(stderr_task, "cancel", None)
                if callable(cancel):
                    with suppress(Exception):
                        cancel()
                wait = getattr(stderr_task, "wait", None)
                if callable(wait):
                    with suppress(Exception):
                        await _maybe_await(wait())
            _set_attr_safely(self, "_stderr_task", None)

        # Close stdin — signals EOF to the CLI subprocess
        write_lock = getattr(self, "_write_lock", None) or _NoopAsyncContext()
        async with write_lock:
            _set_attr_safely(self, "_ready", False)
            stdin_stream = getattr(self, "_stdin_stream", None)
            if stdin_stream:
                with suppress(Exception):
                    await _maybe_await(stdin_stream.aclose())
                _set_attr_safely(self, "_stdin_stream", None)

        stderr_stream = getattr(self, "_stderr_stream", None)
        if stderr_stream:
            with suppress(Exception):
                await _maybe_await(stderr_stream.aclose())
            _set_attr_safely(self, "_stderr_stream", None)

        # Wait for the CLI to exit gracefully after stdin EOF so it can
        # flush the session JSONL.  Only send SIGTERM on timeout.
        wait = getattr(process, "wait", None)
        if getattr(process, "returncode", None) is None and callable(wait):
            try:
                with anyio.fail_after(_GRACEFUL_EXIT_TIMEOUT_SEC):
                    await _maybe_await(wait())
            except TimeoutError:
                logger.debug(
                    "CLI did not exit within %ds after stdin EOF; sending SIGTERM",
                    _GRACEFUL_EXIT_TIMEOUT_SEC,
                )
                terminate = getattr(process, "terminate", None)
                if callable(terminate):
                    with suppress(ProcessLookupError):
                        terminate()
                try:
                    with anyio.fail_after(_GRACEFUL_EXIT_TIMEOUT_SEC):
                        await _maybe_await(wait())
                except TimeoutError:
                    kill = getattr(process, "kill", None)
                    if callable(kill):
                        with suppress(ProcessLookupError):
                            kill()
                    with suppress(Exception):
                        await _maybe_await(wait())

        if active_children is not None:
            with suppress(Exception):
                active_children.discard(process)

        _set_attr_safely(self, "_process", None)
        _set_attr_safely(self, "_stdout_stream", None)
        _set_attr_safely(self, "_stdin_stream", None)
        _set_attr_safely(self, "_stderr_stream", None)
        _set_attr_safely(self, "_exit_error", None)

    SubprocessCLITransport.close = _patched_close  # type: ignore[assignment]
    logger.info(
        "Applied SubprocessCLITransport.close() patch (graceful %ds shutdown before SIGTERM)",
        _GRACEFUL_EXIT_TIMEOUT_SEC,
    )


def _patch_query_stdin_lifecycle() -> None:
    """Patch ``Query.wait_for_result_and_end_input()`` — keep stdin open on Windows.

    Root cause
    ----------
    When hooks and SDK-type MCP servers are both absent, the SDK calls
    ``transport.end_input()`` (stdin close / EOF) immediately after writing
    the user message.  On non-Windows platforms this is harmless because
    hooks are enabled and the SDK already defers stdin closure until the
    first ``ResultMessage``.

    On Windows, hooks are disabled (they crash the session due to control
    protocol pipe instability), so the SDK closes stdin right away.  The
    Claude Code CLI — a Node.js process running behind a ``.cmd`` batch
    wrapper — appears to treat early stdin EOF as a disconnect signal:
    after completing the first API response turn it does *not* proceed
    with tool execution or subsequent turns.  The Python side therefore
    sees ``tool_start`` events but never receives ``tool_end`` or the
    next assistant message, producing a frozen UI that only recovers
    when the 120 s per-message timeout fires.

    Fix
    ---
    Make ``wait_for_result_and_end_input()`` a no-op on Windows.  stdin
    remains open throughout the session and is closed only when
    ``transport.close()`` runs during normal ``ClaudeSDKClient`` teardown.
    This is safe because:

    * No control-protocol messages need to be *sent* (hooks disabled,
      permissions bypassed, no SDK MCP servers).
    * ``transport.close()`` already closes stdin with a 5 s grace period.
    * The CLI continues to write stdout events normally.
    """
    from claude_agent_sdk._internal.query import Query

    if not hasattr(Query, "wait_for_result_and_end_input"):
        logger.warning(
            "Skipping Query.wait_for_result_and_end_input() patch; "
            "SDK Query has no wait_for_result_and_end_input method"
        )
        return

    async def _patched_wait(self: Query) -> None:  # type: ignore[override]
        # Skip stdin closure.  transport.close() will handle it during
        # normal client teardown (disconnect / __aexit__).
        logger.debug(
            "Windows stdin lifecycle patch: skipping early end_input() (hooks=%s, sdk_mcp=%d)",
            bool(self.hooks),
            len(self.sdk_mcp_servers),
        )

    Query.wait_for_result_and_end_input = _patched_wait  # type: ignore[assignment]
    logger.info(
        "Applied Query.wait_for_result_and_end_input() patch (stdin kept open on Windows until session teardown)"
    )


def apply_sdk_transport_patch() -> None:
    """Apply all SDK monkey-patches needed for reliable Windows operation."""
    global _patched  # noqa: PLW0603
    if _patched:
        return

    try:
        _patch_transport_close()
    except ImportError:
        logger.debug("claude_agent_sdk not installed; skipping SDK patches")
        return

    if sys.platform == "win32":
        try:
            _patch_query_stdin_lifecycle()
        except Exception:
            logger.warning(
                "Failed to apply Windows stdin lifecycle patch",
                exc_info=True,
            )

    _patched = True
