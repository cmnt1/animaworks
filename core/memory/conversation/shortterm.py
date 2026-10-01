# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Short-term memory (短期記憶) management.

Handles writing and reading transient session state to the
``{anima_dir}/shortterm/`` folder.  This state bridges across
session restarts when the context window threshold is crossed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.i18n import t
from core.platform.state_writer import get_state_writer, is_task_runner_process, run_writer_sync

logger = logging.getLogger("animaworks.shortterm_memory")

# Maximum characters for accumulated_response in the markdown dump.
_MAX_RESPONSE_CHARS = 8000


@dataclass
class SessionState:
    """State captured from a session for externalization."""

    session_id: str = ""
    timestamp: str = ""
    trigger: str = ""
    original_prompt: str = ""
    accumulated_response: str = ""
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    context_usage_ratio: float = 0.0
    turn_count: int = 0
    notes: str = ""


@dataclass
class StreamCheckpoint:
    """Checkpoint captured during streaming execution for retry on disconnect.

    Records completed tool calls and accumulated text so that a retry
    can resume from where the stream was interrupted.
    """

    timestamp: str = ""
    trigger: str = ""
    original_prompt: str = ""
    completed_tools: list[dict[str, Any]] = field(default_factory=list)
    accumulated_text: str = ""
    retry_count: int = 0


class ShortTermMemory:
    """Manages the short-term memory folder for a DigitalAnima.

    Folder layout::

        {anima_dir}/shortterm/
          ├── session_state.md    # Human-readable (fed to agent)
          ├── session_state.json  # Machine-readable (for programmatic restore)
          └── archive/            # Completed / superseded states
    """

    def __init__(
        self,
        anima_dir: Path,
        session_type: str = "chat",
        thread_id: str = "default",
        *,
        read_only: bool = False,
    ) -> None:
        self.anima_dir = anima_dir
        self.read_only = read_only
        self._session_type = session_type
        self._thread_id = thread_id
        base = anima_dir / "shortterm" / session_type
        if thread_id != "default":
            self.shortterm_dir = base / thread_id
        else:
            self.shortterm_dir = base
        self._archive_dir = self.shortterm_dir / "archive"
        if not self.read_only and not is_task_runner_process():
            self.shortterm_dir.mkdir(parents=True, exist_ok=True)

    async def ensure_ready(self) -> None:
        """Migrate legacy paths through the active state writer before use."""
        await get_state_writer(self.anima_dir).migrate_legacy_shortterm(self._session_type, self._thread_id)

    # ── Query ───────────────────────────────────────────────

    def has_pending(self) -> bool:
        """Check if there is an unresolved short-term memory to restore."""
        return (self.shortterm_dir / "session_state.json").exists()

    # ── Save ────────────────────────────────────────────────

    async def asave(self, state: SessionState) -> Path:
        """Externalize short-term state through the process state writer."""
        path = await get_state_writer(self.anima_dir).save_shortterm(
            self._session_type,
            self._thread_id,
            asdict(state),
            self._render_markdown(state),
        )
        logger.info(
            "Short-term memory saved: %.1f%% context, %d turns",
            state.context_usage_ratio * 100,
            state.turn_count,
        )
        return path

    def save(self, state: SessionState) -> Path:
        """Synchronous compatibility adapter for local callers and tests."""
        writer = get_state_writer(self.anima_dir)
        return run_writer_sync(writer, self.asave(state))

    async def asave_if_not_exists(self, state: SessionState) -> Path | None:
        """Save only if the agent did not already write a state file.

        This acts as a framework-side fallback in case the agent
        ignored the hook's ``additionalContext`` instruction.
        """
        # Check if the agent already wrote session_state.md via its Write tool
        agent_wrote = (self.shortterm_dir / "session_state.md").exists()
        if agent_wrote:
            logger.info("Agent already wrote short-term memory; skipping fallback save")
            return None
        return await self.asave(state)

    def save_if_not_exists(self, state: SessionState) -> Path | None:
        writer = get_state_writer(self.anima_dir)
        return run_writer_sync(writer, self.asave_if_not_exists(state))

    # ── Load ────────────────────────────────────────────────

    def load(self) -> SessionState | None:
        """Load the current short-term memory state."""
        json_path = self.shortterm_dir / "session_state.json"
        if not json_path.exists():
            return None
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return SessionState(**data)
        except (json.JSONDecodeError, TypeError, OSError):
            logger.warning("Failed to parse short-term memory JSON")
            return None

    def load_markdown(self) -> str:
        """Load the markdown dump directly (for system prompt injection)."""
        md_path = self.shortterm_dir / "session_state.md"
        if md_path.exists():
            try:
                return md_path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Failed to read short-term memory markdown from %s", md_path, exc_info=True)
                return ""
        return ""

    def render_for_injection(self) -> str:
        """Render short-term memory for system-prompt injection.

        Prefers the machine-readable ``session_state.json`` (full fidelity),
        applying the same tail-priority truncation as the markdown dump, and
        falls back to the on-disk markdown only when the JSON is missing or
        corrupt. The markdown dump may be written by the agent itself and can
        drift from the framework-managed JSON, so the JSON is authoritative.
        """
        state = self.load()
        if state is not None:
            return self._render_markdown(state)
        return self.load_markdown()

    # ── Clear ───────────────────────────────────────────────

    async def aclear(self) -> None:
        """Archive the current short-term state through the process writer."""
        await get_state_writer(self.anima_dir).archive_shortterm(self._session_type, self._thread_id)
        logger.info("Short-term memory cleared")

    def clear(self) -> None:
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, self.aclear())

    async def aclear_for_clean_start(self) -> None:
        """Archive session state and remove retry checkpoint before a clean run."""
        await get_state_writer(self.anima_dir).archive_shortterm(self._session_type, self._thread_id)
        await get_state_writer(self.anima_dir).clear_stream_checkpoint(self._session_type, self._thread_id)
        logger.info(
            "Short-term clean-start state cleared (session_type=%s, thread_id=%s)",
            self._session_type,
            self._thread_id,
        )

    def clear_for_clean_start(self) -> None:
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, self.aclear_for_clean_start())

    # ── Stream checkpoint ─────────────────────────────────

    _CHECKPOINT_FILE = "stream_checkpoint.json"

    async def asave_checkpoint(self, checkpoint: StreamCheckpoint) -> Path:
        """Persist a streaming checkpoint through the process state writer."""
        path = await get_state_writer(self.anima_dir).save_stream_checkpoint(
            self._session_type,
            self._thread_id,
            asdict(checkpoint),
        )
        logger.debug(
            "Stream checkpoint saved: %d completed tools, retry=%d",
            len(checkpoint.completed_tools),
            checkpoint.retry_count,
        )
        return path

    def save_checkpoint(self, checkpoint: StreamCheckpoint) -> Path:
        writer = get_state_writer(self.anima_dir)
        return run_writer_sync(writer, self.asave_checkpoint(checkpoint))

    def load_checkpoint(self) -> StreamCheckpoint | None:
        """Load the current stream checkpoint, if any."""
        path = self.shortterm_dir / self._CHECKPOINT_FILE
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return StreamCheckpoint(**data)
        except (json.JSONDecodeError, TypeError, OSError):
            logger.warning("Failed to parse stream checkpoint JSON")
            return None

    async def aclear_checkpoint(self) -> None:
        """Remove the stream checkpoint through the process state writer."""
        await get_state_writer(self.anima_dir).clear_stream_checkpoint(self._session_type, self._thread_id)
        logger.debug("Stream checkpoint cleared")

    def clear_checkpoint(self) -> None:
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, self.aclear_checkpoint())

    # ── Private ─────────────────────────────────────────────

    def _migrate_legacy_files(self) -> None:
        """Synchronously migrate old shortterm files for local compatibility."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, writer.migrate_legacy_shortterm(self._session_type, self._thread_id))

    def _archive_existing(self) -> None:
        """Synchronously archive the current files for local compatibility."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, writer.archive_shortterm(self._session_type, self._thread_id))

    def _prune_archive(self, max_files: int = 100) -> None:
        """Synchronously prune archived files for local compatibility."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(
            writer,
            writer.prune_shortterm_archive(self._session_type, self._thread_id, max_files=max_files),
        )

    def _render_markdown(self, state: SessionState) -> str:
        """Render a human-readable markdown dump of the session state."""
        # Truncate accumulated_response if too long
        response = state.accumulated_response
        if len(response) > _MAX_RESPONSE_CHARS:
            response = t("shortterm.ellipsis_omitted") + response[-_MAX_RESPONSE_CHARS:]

        # Tool use summary (last 20)
        tool_lines = ""
        if state.tool_uses:
            entries = []
            for tu in state.tool_uses[-20:]:
                name = tu.get("name", "?")
                inp = str(tu.get("input", ""))[:500]
                entries.append(f"- {name}: {inp}")
                result = str(tu.get("result", ""))[:500]
                if result:
                    entries.append(f"  → {result}")
            tool_lines = "\n".join(entries)

        return f"""\
{t("shortterm.title")}

{t("shortterm.meta_header")}
- {t("shortterm.session_id", value=state.session_id)}
- {t("shortterm.timestamp", value=state.timestamp)}
- {t("shortterm.trigger", value=state.trigger)}
- {t("shortterm.context_usage", value=f"{state.context_usage_ratio:.0%}")}
- {t("shortterm.turn_count", value=state.turn_count)}

{t("shortterm.original_request")}
{state.original_prompt}

{t("shortterm.work_so_far")}
{t("shortterm.already_sent_note")}
{response}

{t("shortterm.tools_used_recent")}
{tool_lines or t("shortterm.none")}

{t("shortterm.notes_header")}
{state.notes or t("shortterm.none")}
"""
