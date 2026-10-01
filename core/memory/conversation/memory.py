# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Conversation memory (会話記憶 / ワーキングメモリ) management.

Maintains a rolling history of chat turns per DigitalAnima.
When the accumulated history exceeds the configured threshold,
older turns are compressed into an LLM-generated summary while
recent turns are kept verbatim.

Storage: ``{anima_dir}/state/conversation.json``
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, ClassVar

from core.i18n import t
from core.memory.conversation.compression import (
    CompressionResult,
)
from core.memory.conversation.compression import (
    _compress as _compress_fn,
)
from core.memory.conversation.compression import (
    compress_if_needed as _compress_if_needed,
)
from core.memory.conversation.compression import (
    compress_if_needed_detailed as _compress_if_needed_detailed,
)
from core.memory.conversation.compression import (
    needs_compression as _needs_compression,
)
from core.memory.conversation.finalize import (
    finalize_if_session_ended as _finalize_if_session_ended,
)
from core.memory.conversation.finalize import finalize_session as _finalize_session
from core.memory.conversation.models import (
    _CHARS_PER_TOKEN,
    _ERROR_PATTERN,
    _MAX_DISPLAY_TURNS,
    _MAX_HUMAN_CHARS_IN_HISTORY,
    _MAX_RENDERED_TOOL_RECORDS,
    _MAX_RESPONSE_CHARS_IN_HISTORY,
    _MAX_STORED_CONTENT_CHARS,
    _MAX_TOOL_INPUT_SUMMARY,
    _MAX_TOOL_RECORDS_PER_TURN,
    _MAX_TOOL_RESULT_SUMMARY,
    _RESOLVED_PATTERN,
    SESSION_GAP_MINUTES,
    ConversationState,
    ConversationTurn,
    ToolRecord,
)
from core.memory.conversation.prompt import (
    build_chat_prompt as _build_chat_prompt,
)
from core.memory.conversation.prompt import (
    build_structured_messages as _build_structured_messages,
)
from core.platform.state_writer import get_state_writer, run_writer_sync
from core.schemas import ModelConfig

logger = logging.getLogger("animaworks.conversation_memory")


class ConversationMemory:
    """Manages per-anima conversation history with automatic compression."""

    _class_locks: ClassVar[dict[str, asyncio.Lock]] = {}

    def __init__(
        self,
        anima_dir: Path,
        model_config: ModelConfig,
        thread_id: str = "default",
    ) -> None:
        self.anima_dir = anima_dir
        self.anima_name = anima_dir.name
        self.model_config = model_config
        self.thread_id = thread_id
        self._state_dir = anima_dir / "state"
        if thread_id == "default":
            self._state_path = self._state_dir / "conversation.json"
        else:
            self._state_path = self._state_dir / "conversations" / f"{thread_id}.json"
        self._transcript_dir = anima_dir / "transcripts"
        self._state: ConversationState | None = None

        _key = f"{anima_dir}:{thread_id}"
        if _key not in self.__class__._class_locks:
            self.__class__._class_locks[_key] = asyncio.Lock()
        self._finalize_lock = self.__class__._class_locks[_key]

    @staticmethod
    async def _call_llm(system: str, user_content: str, max_tokens: int = 1000) -> str:
        """Delegate to standalone _call_llm for backward compat."""
        from core.memory.conversation.compression import _call_llm

        return await _call_llm(system, user_content, max_tokens=max_tokens)

    def _load_context_window_overrides(self) -> dict[str, int] | None:
        try:
            from core.config.models import load_config

            config = load_config()
            return config.model_context_windows or None
        except Exception:
            return None

    def load(self) -> ConversationState:
        if self._state is not None:
            return self._state

        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                turns = []
                for t in data.get("turns", []):
                    raw_records = t.get("tool_records", [])
                    filtered = {k: v for k, v in t.items() if k != "tool_records"}
                    turn = ConversationTurn(**filtered)
                    turn.tool_records = [ToolRecord(**r) for r in raw_records]
                    turns.append(turn)
                self._state = ConversationState(
                    anima_name=data.get("anima_name", self.anima_name),
                    turns=turns,
                    compressed_summary=data.get("compressed_summary", ""),
                    compressed_turn_count=data.get("compressed_turn_count", 0),
                    last_finalized_turn_index=data.get("last_finalized_turn_index", 0),
                )
            except (json.JSONDecodeError, TypeError, OSError):
                logger.warning("Failed to parse conversation state; starting fresh")
                self._state = ConversationState(anima_name=self.anima_name)
        else:
            self._state = ConversationState(anima_name=self.anima_name)

        return self._state

    def _serialized_state(self) -> dict[str, Any]:
        state = self.load()
        return {
            "anima_name": state.anima_name,
            "turns": [asdict(t) for t in state.turns],
            "compressed_summary": state.compressed_summary,
            "compressed_turn_count": state.compressed_turn_count,
            "last_finalized_turn_index": state.last_finalized_turn_index,
        }

    async def asave(self) -> None:
        """Persist the current conversation through the process state writer."""
        await get_state_writer(self.anima_dir).save_conversation(self.thread_id, self._serialized_state())

    def save(self) -> None:
        """Synchronous compatibility adapter for local callers and tests."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, self.asave())

    @staticmethod
    def _valid_date(date: str) -> bool:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", date))

    def load_transcript(self, date: str) -> list[dict]:
        if not self._valid_date(date):
            logger.warning("Invalid transcript date format: %s", date)
            return []
        path = self._transcript_dir / f"{date}.jsonl"
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            logger.warning("Failed to read transcript from %s", path, exc_info=True)
            return []
        messages = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed transcript line in %s", path)
        return messages

    async def awrite_transcript(
        self,
        role: str,
        content: str,
        *,
        from_person: str = "",
        thread_id: str = "default",
        attachments: list[str] | None = None,
        tool_names: list[str] | None = None,
    ) -> None:
        from core.time_utils import now_iso

        entry: dict[str, Any] = {
            "ts": now_iso(),
            "role": role,
            "content": content,
        }
        if from_person:
            entry["from"] = from_person
        if thread_id and thread_id != "default":
            entry["thread_id"] = thread_id
        if attachments:
            entry["attachments"] = attachments
        if tool_names:
            entry["tool_names"] = tool_names

        try:
            await get_state_writer(self.anima_dir).append_transcript(entry)
        except OSError:
            logger.warning("Failed to write transcript entry", exc_info=True)

    def write_transcript(
        self,
        role: str,
        content: str,
        *,
        from_person: str = "",
        thread_id: str = "default",
        attachments: list[str] | None = None,
        tool_names: list[str] | None = None,
    ) -> None:
        """Synchronous compatibility adapter for local callers and tests."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(
            writer,
            self.awrite_transcript(
                role,
                content,
                from_person=from_person,
                thread_id=thread_id,
                attachments=attachments,
                tool_names=tool_names,
            ),
        )

    def append_turn(
        self,
        role: str,
        content: str,
        attachments: list[str] | None = None,
        tool_records: list[ToolRecord] | None = None,
    ) -> None:
        state = self.load()
        if len(content) > _MAX_STORED_CONTENT_CHARS:
            logger.info(
                "Truncating %s turn content from %d to %d chars",
                role,
                len(content),
                _MAX_STORED_CONTENT_CHARS,
            )
            content = content[:_MAX_STORED_CONTENT_CHARS] + t("conversation.truncated_suffix", length=len(content))
        records = tool_records or []
        if len(records) > _MAX_TOOL_RECORDS_PER_TURN:
            records = records[:_MAX_TOOL_RECORDS_PER_TURN]
        turn = ConversationTurn(
            role=role,
            content=content,
            attachments=attachments or [],
            tool_records=records,
        )
        state.turns.append(turn)

    async def aclear(self) -> None:
        self._state = ConversationState(anima_name=self.anima_name)
        await get_state_writer(self.anima_dir).clear_conversation(self.thread_id)
        logger.info("Conversation memory cleared for %s", self.anima_name)

    def clear(self) -> None:
        """Synchronous compatibility adapter for local callers and tests."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, self.aclear())

    def build_chat_prompt(
        self,
        content: str,
        from_person: str = "human",
        max_history_chars: int | None = None,
    ) -> str:
        state = self.load()
        return _build_chat_prompt(state, content, from_person, max_history_chars, self.model_config)

    def build_structured_messages(self, content: str, fmt: str = "openai") -> list[dict[str, Any]]:
        state = self.load()
        return _build_structured_messages(state, content, fmt, self.model_config)

    async def _compress(self) -> CompressionResult:
        return await _compress_fn(self.load(), self.model_config, self.asave, self.anima_name)

    def needs_compression(self) -> bool:
        state = self.load()
        return _needs_compression(state, self.model_config, self._load_context_window_overrides)

    async def compress_if_needed(self) -> bool:
        return await _compress_if_needed(
            self.load(),
            self.model_config,
            self._load_context_window_overrides,
            self.asave,
            self.anima_name,
        )

    async def compress_if_needed_detailed(self) -> CompressionResult:
        return await _compress_if_needed_detailed(
            self.load(),
            self.model_config,
            self._load_context_window_overrides,
            self.asave,
            self.anima_name,
        )

    async def finalize_if_session_ended(self) -> bool:
        async def _compress_inner() -> CompressionResult:
            from core.memory.conversation.compression import _compress

            return await _compress(self.load(), self.model_config, self.asave, self.anima_name)

        async def _finalize_inner() -> bool:
            return await _finalize_session(
                self.anima_dir,
                self.load(),
                self.model_config,
                self.asave,
            )

        return await _finalize_if_session_ended(
            self._finalize_lock,
            self.load,
            self.asave,
            self.needs_compression,
            _compress_inner,
            _finalize_inner,
            self.anima_name,
        )
