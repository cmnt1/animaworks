from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Mode Y executor: Google Antigravity CLI (``agy``) wrapper.

Runs ``agy`` as a subprocess with ``--output-format stream-json`` and
``--input-format stream-json``.  The user prompt is written to stdin as one
NDJSON line so prompts larger than the argv limit keep working.  The system
prompt and the AnimaWorks MCP server are injected through a per-turn custom
agent definition under ``<workspace>/.agents/agents/``.
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.execution.base import ExecutionResult, TokenUsage, ToolCallRecord, _truncate_for_record
from core.execution.cli_stream import CLIStreamExecutor
from core.execution.engine_base import GRACEFUL_KILL_WAIT_SECONDS, engine_error_event
from core.execution.events import done_event, text_delta_event, tool_end_event, tool_start_event
from core.execution.mcp_env import build_mcp_env
from core.execution.process_runner import ProcessRunner
from core.execution.session.engine_session import MAX_RESUME_TURNS, aload_turn_limited_session, next_turn_count
from core.execution.session.session_context import _resolve_session_type
from core.execution.session.session_ids import EngineSessionIds
from core.i18n import t
from core.platform.agy import find_agy_binary as _find_agy_binary
from core.platform.agy import is_agy_cli_available
from core.platform.subprocess_entries import SubprocessEntry, module_args
from core.prompt.context import ContextTracker
from core.schemas import ImageData, ModelConfig

logger = logging.getLogger("animaworks.execution.agy_cli")

__all__ = ["AgyCLIExecutor", "is_agy_cli_available"]

# ── Constants ───────────────────────────────────────────────────

_MAX_RESUME_TURNS = MAX_RESUME_TURNS
_AGY_SESSION_IDS = EngineSessionIds("agy")
_AGY_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
_AGY_EFFORT_SUFFIXES = ("-low", "-medium", "-high")
_AGY_AUTH_WORDS = ("auth", "login", "unauthorized", "unauthenticated", "oauth", "credential")
_AGY_QUOTA_WORDS = ("quota", "rate limit", "resource_exhausted", "429", "credits", "credit")
_AGY_TOOL_ACTIVE_STATES = frozenset({"ACTIVE", "PENDING", "RUNNING", "STARTED", "IN_PROGRESS"})
_AGY_STALE_AGENT_SECONDS = 24 * 60 * 60
_AGY_SETTINGS = {
    "artifactReviewPolicy": "always-proceed",
    "allowNonWorkspaceAccess": True,
    "showTips": False,
    "notifications": False,
    "showFeedbackSurvey": False,
}
# Built-in tools exposed to the custom agent.  ``manage_task`` and
# ``call_mcp_tool`` are added automatically by agy.
_AGY_BUILTIN_TOOLS = (
    "run_command",
    "command_status",
    "send_command_input",
    "view_file",
    "list_dir",
    "find_by_name",
    "grep_search",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
    "read_url_content",
    "search_web",
    "wait",
)
_RESUME_AGENT_BODY = "# AnimaWorks Anima\n\nContinue the existing conversation.\n"


def _resolve_agy_model(model: str) -> str:
    """Strip AnimaWorks' ``agy/`` provider prefix for the CLI."""
    return model[len("agy/") :] if model.startswith("agy/") else model


def _format_current_time() -> str:
    """Return a short time-stamp line prepended to every user prompt."""
    from core.time_utils import now_local

    return "[" + now_local().strftime("%Y-%m-%d %H:%M %Z") + "]"


@dataclass(frozen=True)
class _TurnOutcome:
    """One agy process result plus the state needed for session handling."""

    result: ExecutionResult
    session_id: str | None
    failed: bool
    context_usage: dict[str, int] | None


# ── Executor ───────────────────────────────────────────────────


class AgyCLIExecutor(CLIStreamExecutor):
    """Execute via Google Antigravity CLI (Mode Y).

    Each turn writes a fresh custom agent definition (system prompt and MCP
    server) and streams NDJSON from ``agy``.  The conversation ID is persisted
    so later chat turns resume with ``--conversation``.
    """

    engine_mode = "Y"
    session_engine = "agy"

    @property
    def supports_streaming(self) -> bool:  # noqa: D102
        return True

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
        self._workspace = anima_dir / ".agy-workspace"

    # ── Helpers ─────────────────────────────────────────────────

    def _find_binary(self) -> str | None:
        """Return path to the agy binary, or None."""
        return _find_agy_binary()

    def _ensure_workspace(self) -> None:
        """Create the agy workspace and agent-definition directories."""
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._agents_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _agents_dir(self) -> Path:
        return self._workspace / ".agents" / "agents"

    def _cleanup_stale_agents(self) -> None:
        """Remove per-turn agent definitions left behind by old runs."""
        cutoff = time.time() - _AGY_STALE_AGENT_SECONDS
        for path in self._agents_dir.glob("aw-*.md"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                logger.debug("Could not remove stale agy agent definition %s", path, exc_info=True)

    def _agent_name(self) -> str:
        """Return a fresh agent name matching ``^[a-z][-a-z0-9]*$``."""
        return f"aw-{uuid.uuid4().hex[:8]}"

    def _mcp_server_name(self) -> str:
        """Return a per-anima MCP server name matching agy's safe character set."""
        anima_name = self._anima_dir.name.lower()
        safe = re.sub(r"[^a-z0-9-]", "-", anima_name).strip("-")
        return f"aw-{safe or 'anima'}"

    def _build_agent_frontmatter(self, agent_name: str) -> dict[str, Any]:
        """Build YAML-safe frontmatter for the custom agent definition."""
        return {
            "name": agent_name,
            "description": "AnimaWorks anima",
            "mainAgent": True,
            "subagent": False,
            "commandExecutionPolicy": "auto",
            "tools": list(_AGY_BUILTIN_TOOLS),
            "mcpServers": [
                {
                    "name": self._mcp_server_name(),
                    "command": sys.executable,
                    "args": list(module_args(SubprocessEntry.MCP_SERVER)),
                    "env": build_mcp_env(self._anima_dir),
                }
            ],
        }

    def _write_agent_definition(self, agent_name: str, body: str) -> Path:
        """Write the custom agent Markdown and return its path."""
        self._agents_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = yaml.safe_dump(
            self._build_agent_frontmatter(agent_name),
            sort_keys=False,
            allow_unicode=True,
        )
        path = self._agents_dir / f"{agent_name}.md"
        path.write_text(f"---\n{frontmatter}---\n{body}\n", encoding="utf-8")
        return path

    def _resolve_effort(self) -> str | None:
        """Resolve the agy ``--effort`` value from model config or models.json."""
        effort = (self._model_config.extra_keys or {}).get("agy_effort")
        if not effort:
            try:
                from core.config.model_mode import _match_models_json

                model_entry = _match_models_json(self._model_config.model) or {}
            except Exception:
                logger.debug("Could not read models.json effort for agy model", exc_info=True)
                model_entry = {}
            effort = model_entry.get("reasoning_effort") or self._model_config.thinking_effort
        if not effort:
            return None
        value = str(effort).strip().lower()
        return value if value in _AGY_EFFORTS else None

    def _build_command(self, *, agent_name: str, resume_id: str | None = None) -> list[str]:
        """Build the agy argv.  ``-p=`` must be the final argument."""
        binary = self._find_binary()
        if not binary:
            return []
        model = _resolve_agy_model(self._model_config.model)
        cmd = [
            binary,
            "--agent",
            agent_name,
            "--model",
            model,
        ]
        effort = self._resolve_effort()
        if effort and not model.lower().endswith(_AGY_EFFORT_SUFFIXES):
            cmd.extend(["--effort", effort])
        cmd.extend(
            [
                "--output-format",
                "stream-json",
                "--input-format",
                "stream-json",
                "--dangerously-skip-permissions",
                "--disable-slash-commands",
                "--settings",
                json.dumps(_AGY_SETTINGS, ensure_ascii=True, separators=(",", ":")),
            ]
        )
        if resume_id:
            cmd.extend(["--conversation", resume_id])
        cmd.append("-p=")
        return cmd

    def _build_env(self) -> dict[str, str]:
        """Return the child environment, delegating HOME and auth to agy."""
        env = dict(os.environ)
        from core.execution.github_identity import resolve_github_token_env
        from core.execution.workspace_env import update_workspace_env

        update_workspace_env(env, self._anima_dir)
        env.update(resolve_github_token_env(self._anima_dir))
        api_key = self._model_config.api_key
        if not api_key and self._model_config.api_key_env:
            api_key = os.environ.get(self._model_config.api_key_env)
        if api_key:
            env["GEMINI_API_KEY"] = api_key
        return env

    @staticmethod
    def _stdin_payload(prompt: str) -> bytes:
        """Encode the single NDJSON user-input line written to agy's stdin."""
        payload = {
            "event": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            },
        }
        return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")

    @staticmethod
    async def _write_stdin(proc: asyncio.subprocess.Process, prompt: str) -> None:
        """Write the prompt line and close stdin so agy starts processing."""
        stdin = proc.stdin
        if stdin is None:
            return
        try:
            stdin.write(AgyCLIExecutor._stdin_payload(prompt))
            await stdin.drain()
            stdin.close()
        except (BrokenPipeError, ConnectionError, OSError):
            logger.debug("agy stdin closed before the prompt could be written", exc_info=True)

    def _save_images(self, images: list[ImageData] | None) -> list[Path]:
        """Persist image payloads and return path references for the prompt."""
        if not images:
            return []
        directory = self._workspace / "attachments"
        directory.mkdir(parents=True, exist_ok=True)
        prefix = uuid.uuid4().hex[:8]
        paths: list[Path] = []
        for index, image in enumerate(images):
            media_type = str(image.get("media_type") or "image/png")
            extension = media_type.split("/")[-1].split(";")[0] or "png"
            if extension == "jpeg":
                extension = "jpg"
            try:
                data = base64.b64decode(image.get("data") or "")
            except (ValueError, TypeError):
                logger.debug("Ignoring malformed agy image payload at index %d", index)
                continue
            path = directory / f"agy-image-{prefix}-{index}.{extension}"
            path.write_bytes(data)
            paths.append(path)
        return paths

    @staticmethod
    def _summarize(value: Any) -> str:
        """Render tool input/output for a compact record summary."""
        if value is None:
            return ""
        if isinstance(value, str):
            return _truncate_for_record(value, 500)
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
        return _truncate_for_record(text, 500)

    @staticmethod
    def _usage_from_result(result: dict[str, Any] | None) -> TokenUsage:
        """Convert the result event's usage object into the shared model."""
        if not isinstance(result, dict):
            return TokenUsage()
        usage = result.get("usage")
        if isinstance(usage, dict):
            return TokenUsage(
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                cache_read_tokens=int(usage.get("cache_read_tokens", 0) or 0),
            )
        return TokenUsage(
            input_tokens=int(result.get("input_tokens", 0) or 0),
            output_tokens=int(result.get("output_tokens", 0) or 0),
            cache_read_tokens=int(result.get("cache_read_tokens", 0) or 0),
        )

    @staticmethod
    def _context_usage(usage: dict[str, Any] | None) -> dict[str, int] | None:
        """Build the ContextTracker usage dict from the last agent response."""
        if not isinstance(usage, dict):
            return None
        return {
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_tokens", 0) or 0),
        }

    def _reason_for_error(self, message: str) -> str:
        """Classify an agy failure, matching Grok's provider reason taxonomy."""
        metadata = self._error_metadata(message)
        reason = str(metadata.get("reason") or "unknown")
        lowered = message.lower()
        if any(word in lowered for word in _AGY_AUTH_WORDS):
            return "auth"
        if any(word in lowered for word in _AGY_QUOTA_WORDS):
            try:
                from core.llm.guard.error_classifier import classify_llm_error_message

                classified = classify_llm_error_message(message)[0].value
            except Exception:
                logger.debug("Could not classify agy quota error", exc_info=True)
                classified = "unknown"
            if classified != "unknown":
                return classified
            if "quota" in lowered:
                return "quota_exhausted"
            if "credit" in lowered:
                return "billing"
            return "rate_limit"
        return reason

    def _auth_error(self, message: str) -> bool:
        lowered = message.lower()
        return any(word in lowered for word in _AGY_AUTH_WORDS)

    # ── Turn orchestration ──────────────────────────────────────

    async def _execute_cli_turn(
        self,
        *,
        prompt: str,
        system_prompt: str,
        tracker: ContextTracker,
        trigger: str,
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        thread_id: str = "default",
        _event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> ExecutionResult:
        """Run one logical turn, including the single resume retry."""
        if self._check_interrupted():
            return ExecutionResult(text="[Session interrupted by user]")

        if not self._find_binary():
            error_text = t("agy_cli.not_installed")
            await self._emit(_event_sink, text_delta_event(error_text))
            self._error_metadata(error_text)
            return ExecutionResult(text=error_text, error=True, reason="unknown")

        self._ensure_workspace()
        self._cleanup_stale_agents()
        session_type = _resolve_session_type(trigger)
        decision = await aload_turn_limited_session(self._anima_dir, "agy", trigger, thread_id)
        resume_id = decision.session_id

        image_paths = self._save_images(images)
        try:
            prompt_text = _format_current_time() + "\n\n" + prompt
            if image_paths:
                references = "\n".join(t("agy_cli.image_attachment", path=path.resolve()) for path in image_paths)
                prompt_text = f"{prompt_text}\n\n{references}"

            message = self._build_message(prompt_text, prior_messages)
            agent_body = _RESUME_AGENT_BODY if resume_id else (system_prompt or _RESUME_AGENT_BODY)
            outcome = await self._run_subprocess(
                agent_body,
                message,
                resume_id=resume_id,
                event_sink=_event_sink,
            )

            retried = False
            if outcome.failed and resume_id:
                logger.warning(
                    "agy conversation %s failed to resume; retrying with a fresh session",
                    resume_id[:12],
                )
                await _AGY_SESSION_IDS.aclear(self._anima_dir, session_type, thread_id)
                outcome = await self._run_subprocess(
                    system_prompt or _RESUME_AGENT_BODY,
                    message,
                    resume_id=None,
                    event_sink=_event_sink,
                )
                retried = True

            if tracker is not None and outcome.context_usage is not None:
                tracker.update_from_message_start(outcome.context_usage)

            new_turn, rotation_pending = next_turn_count(
                decision,
                resumed=resume_id is not None,
                rotated_during_run=retried,
            )
            if outcome.session_id and decision.resumable and not outcome.failed:
                await _AGY_SESSION_IDS.asave(
                    self._anima_dir,
                    outcome.session_id,
                    session_type,
                    thread_id,
                    turn_count=new_turn,
                )
                logger.debug(
                    "Saved agy conversation %s turn=%d for %s/%s",
                    outcome.session_id[:12],
                    new_turn,
                    session_type,
                    thread_id,
                )

            outcome.result.session_rotation_pending = rotation_pending
            return outcome.result
        finally:
            for path in image_paths:
                path.unlink(missing_ok=True)

    @staticmethod
    def _build_message(prompt: str, prior_messages: list[dict[str, Any]] | None) -> str:
        """Append prior-message context when the engine receives it explicitly."""
        if not prior_messages:
            return prompt
        lines: list[str] = []
        for entry in prior_messages:
            role = str(entry.get("role") or "user")
            content = entry.get("content")
            if isinstance(content, list):
                content = "\n".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            if content:
                lines.append(f"{role}: {content}")
        if not lines:
            return prompt
        return "\n\n".join(lines) + "\n\n" + prompt

    @staticmethod
    async def _emit(
        sink: Callable[[dict[str, Any]], Awaitable[None]] | None,
        event: dict[str, Any],
    ) -> None:
        if sink is not None:
            await sink(event)

    # ── Subprocess ──────────────────────────────────────────────

    async def _run_subprocess(
        self,
        agent_body: str,
        prompt_text: str,
        *,
        resume_id: str | None,
        event_sink: Callable[[dict[str, Any]], Awaitable[None]] | None,
    ) -> _TurnOutcome:
        """Spawn agy, parse its NDJSON stream, and return the turn outcome."""
        agent_name = self._agent_name()
        agent_path = self._write_agent_definition(agent_name, agent_body)
        cmd = self._build_command(agent_name=agent_name, resume_id=resume_id)
        env = self._build_env()

        text_parts: list[str] = []
        result_payload: dict[str, Any] | None = None
        last_agent_usage: dict[str, Any] | None = None
        session_id: str | None = None
        tool_records: list[ToolCallRecord] = []
        pending_tools: dict[str, dict[str, Any]] = {}
        proc: asyncio.subprocess.Process | None = None
        process_runner = ProcessRunner(graceful_timeout=GRACEFUL_KILL_WAIT_SECONDS)

        async def _emit(event: dict[str, Any]) -> None:
            await self._emit(event_sink, event)

        def _finish(
            *,
            text: str,
            error: bool,
            reason: str,
            failed: bool,
            usage: TokenUsage | None = None,
        ) -> _TurnOutcome:
            return _TurnOutcome(
                result=ExecutionResult(
                    text=text,
                    tool_call_records=tool_records,
                    usage=usage,
                    error=error,
                    reason=reason,
                ),
                session_id=session_id,
                failed=failed,
                context_usage=self._context_usage(last_agent_usage),
            )

        try:
            proc = await process_runner.start(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self._workspace),
            )
            await self._write_stdin(proc, prompt_text)

            try:
                async for line in self.iter_lines(proc.stdout):
                    if self._check_interrupted():
                        await self._kill_process(proc)
                        text = "".join(text_parts) or "[Session interrupted by user]"
                        return _finish(text=text, error=False, reason="", failed=False)

                    event = self._parse_ndjson_event(line)
                    if event is None:
                        continue
                    event_type = event.get("event")

                    if event_type == "init":
                        init = event.get("init")
                        init = init if isinstance(init, dict) else {}
                        conversation_id = event.get("conversation_id") or init.get("conversation_id")
                        if conversation_id:
                            session_id = str(conversation_id)
                        continue

                    if event_type == "step_update":
                        step_update = event.get("step_update")
                        if not isinstance(step_update, dict):
                            continue
                        state = str(step_update.get("state") or "").upper()
                        step_type = str(step_update.get("step_type") or "").lower()
                        step_index = step_update.get("step_index")

                        if step_type == "agent_response":
                            delta = step_update.get("text_delta")
                            if delta:
                                text_parts.append(str(delta))
                                await _emit(text_delta_event(str(delta)))
                            if state == "DONE":
                                usage = step_update.get("usage")
                                last_agent_usage = usage if isinstance(usage, dict) else None
                            continue

                        if step_type != "tool":
                            continue

                        tool_info = step_update.get("tool_info")
                        tool_info = tool_info if isinstance(tool_info, dict) else {}
                        tool_name = str(step_update.get("tool_name") or tool_info.get("name") or "unknown")
                        parameters = tool_info.get("parameters")
                        parameters = parameters if isinstance(parameters, dict) else {}
                        if tool_name == "call_mcp_tool":
                            tool_name = str(parameters.get("ToolName") or tool_name)
                            arguments = parameters.get("Arguments")
                            tool_input: Any = arguments if isinstance(arguments, dict) else {"Arguments": arguments}
                        else:
                            tool_input = parameters
                        tool_id = str(step_index if step_index is not None else len(pending_tools) + len(tool_records))

                        if state in _AGY_TOOL_ACTIVE_STATES:
                            if tool_id not in pending_tools:
                                pending_tools[tool_id] = {"name": tool_name, "input": tool_input}
                                await _emit(tool_start_event(tool_name, tool_id, input=tool_input))
                            continue

                        if not pending_tools.pop(tool_id, None):
                            await _emit(tool_start_event(tool_name, tool_id, input=tool_input))
                        is_error = state != "DONE"
                        output = tool_info.get("output")
                        record = ToolCallRecord(
                            tool_name=tool_name,
                            tool_id=tool_id,
                            input_summary=self._summarize(tool_input),
                            result_summary=self._summarize(output),
                            is_error=is_error,
                        )
                        tool_records.append(record)
                        await _emit(
                            tool_end_event(
                                tool_name,
                                tool_id,
                                result=record.result_summary,
                                is_error=record.is_error,
                            )
                        )
                        continue

                    if event_type == "result":
                        payload = event.get("result")
                        if isinstance(payload, dict):
                            result_payload = payload
                            conversation_id = payload.get("conversation_id") or event.get("conversation_id")
                            if conversation_id:
                                session_id = str(conversation_id)
            except TimeoutError:
                logger.warning("agy timed out after %ss", self.event_idle_timeout_seconds)
                await self._kill_process(proc)
                await process_runner.close()
                timeout_msg = t("agy_cli.timeout", timeout=self.event_idle_timeout_seconds)
                existing = "".join(text_parts)
                timeout_text = f"{existing}\n\n{timeout_msg}" if existing else timeout_msg
                await _emit(text_delta_event(timeout_msg if not existing else f"\n\n{timeout_msg}"))
                return _finish(text=timeout_text, error=True, reason="timeout", failed=True)

            await proc.wait()
            await process_runner.close()
            stderr_bytes = await process_runner.stderr()
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            status = ""
            error_detail = ""
            response = ""
            if isinstance(result_payload, dict):
                status = str(result_payload.get("status") or "").upper()
                error_detail = str(result_payload.get("error") or result_payload.get("message") or "")
                response = str(result_payload.get("response") or "")
            usage = self._usage_from_result(result_payload)
            streamed_text = "".join(text_parts)
            final_text = response or streamed_text

            status_error = status == "ERROR"
            exit_code = getattr(proc, "returncode", None)
            exit_error = isinstance(exit_code, int) and exit_code != 0
            failed = status_error or (exit_error and not final_text)

            if status_error or exit_error:
                detail = error_detail or stderr_text.strip()
                if exit_code and not detail:
                    detail = f"agy exited with code {exit_code}"
                reason = self._reason_for_error(detail or final_text)
                if self._auth_error(detail or final_text):
                    error_text = t("agy_cli.not_authenticated")
                    final_text = f"{final_text}\n\n{error_text}" if final_text else error_text
                    await _emit(text_delta_event(error_text if not streamed_text else f"\n\n{error_text}"))
                elif not final_text:
                    final_text = f"[agy CLI Error: {detail}]"
                    await _emit(text_delta_event(final_text))
                logger.warning("agy failed (%s): %s", status or exit_code, (detail or "")[:500])
                return _finish(
                    text=final_text,
                    error=True,
                    reason=reason,
                    failed=failed,
                    usage=usage,
                )

            if response and not streamed_text:
                await _emit(text_delta_event(response))
            return _finish(text=final_text, error=False, reason="", failed=False, usage=usage)

        except FileNotFoundError:
            error_text = t("agy_cli.not_installed")
            await _emit(text_delta_event(error_text))
            self._error_metadata(error_text)
            return _finish(text=error_text, error=True, reason="unknown", failed=True)
        except Exception as exc:
            logger.exception("agy execution error")
            reason = self._reason_for_error(str(exc))
            error_text = f"[agy CLI Error: {exc}]"
            await _emit(text_delta_event(error_text))
            return _finish(text=error_text, error=True, reason=reason, failed=True)
        finally:
            if proc is not None:
                await process_runner.close()
            agent_path.unlink(missing_ok=True)

    # ── Streaming adapter ───────────────────────────────────────

    async def _stream_events(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        trigger: str = "",
        thread_id: str = "default",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream normalized agy events while the child is running."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def _run_turn() -> ExecutionResult:
            try:
                return await self._execute_cli_turn(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    tracker=tracker,
                    trigger=trigger,
                    images=images,
                    prior_messages=prior_messages,
                    thread_id=thread_id,
                    _event_sink=queue.put,
                )
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(_run_turn())
        streamed_text = False
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                streamed_text = streamed_text or event.get("type") == "text_delta"
                yield event
            result = await task
            if result.text and not streamed_text:
                yield text_delta_event(result.text)
            if result.error:
                yield engine_error_event(result.text, {"terminal": True, "reason": result.reason})
            yield done_event(
                result.text,
                **({"error": True, "reason": result.reason} if result.error else {}),
                result_message=result.result_message,
                replied_to_from_transcript=result.replied_to_from_transcript,
                tool_call_records=[record.__dict__ for record in result.tool_call_records],
                usage=result.usage.to_dict() if result.usage else None,
                session_rotation_pending=result.session_rotation_pending,
                truncated=result.truncated,
                stop_kind="interrupted" if self._check_interrupted() else "normal",
            )
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
