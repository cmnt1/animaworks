from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Memory consolidation engine — pre/post-processing helpers.

The actual consolidation (episode summarisation, knowledge extraction,
contradiction checks, etc.) is now performed by the Anima itself through
its tool-call loop (see ``Anima.run_consolidation()``).

This module retains:
- Recent episode collection and durable episode write helpers
- Activity collection and budgeting for daily episode extraction
- Knowledge merge-candidate discovery for weekly consolidation
- LLM output sanitisation (shared utility used by reconsolidation.py)
"""

import hashlib
import json
import logging
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from core.time_utils import ensure_aware, get_app_timezone, now_local

logger = logging.getLogger("animaworks.consolidation")


def list_project_archives(anima_dir: Path) -> list[str]:
    """List project archive names found below episodes/projects/."""
    projects_dir = Path(anima_dir) / "episodes" / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(path.name for path in projects_dir.iterdir() if path.is_dir())


# ── ConsolidationEngine ────────────────────────────────────────


class ConsolidationEngine:
    """Pre/post-processing helpers for memory consolidation.

    The Anima itself now drives the consolidation loop via tool calls.
    This class provides daily episode collection and writes, activity
    budgeting, weekly merge-candidate discovery, and shared output
    sanitisation utilities.
    """

    def __init__(
        self,
        anima_dir: Path,
        anima_name: str,
        *,
        rag_store: Any | None = None,
        project: str | None = None,
    ) -> None:
        """Initialize consolidation engine.

        Args:
            anima_dir: Path to anima's directory (~/.animaworks/animas/{name})
            anima_name: Name of the anima for logging
            rag_store: Optional shared RAG vector store instance.
                When provided, avoids re-creating the singleton internally.
        """
        if project is not None and (not isinstance(project, str) or re.fullmatch(r"[A-Za-z0-9_-]+", project) is None):
            raise ValueError("project must contain only letters, numbers, underscores, or hyphens")
        self.anima_dir = anima_dir
        self.anima_name = anima_name
        self.project = project
        self._rag_store = rag_store
        self.episodes_dir = anima_dir / "episodes"
        self.knowledge_dir = anima_dir / "knowledge"
        if project is not None:
            self.episodes_dir /= Path("projects", project)
            self.knowledge_dir /= Path("projects", project)
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

    # ── Daily episode write helpers ──────────────────────────────

    RAW_NOTES_HEADER = "## Raw notes (preserved)"
    CONSOLIDATED_TIMELINE_HEADER = "## Consolidated timeline"

    def unprocessed_activity_chunks(self, target_date: date, chunks: list[str]) -> list[str]:
        """Exclude inputs whose episode was durably written by an earlier run."""
        checkpoint = self._load_episode_checkpoint()
        processed = set(checkpoint.get(target_date.isoformat(), []))
        return [chunk for chunk in chunks if hashlib.sha256(chunk.encode()).hexdigest() not in processed]

    def _load_episode_checkpoint(self) -> dict[str, list[str]]:
        path = self.anima_dir / "state" / "consolidation_episode_checkpoint.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return (
                {
                    key: values
                    for key, values in data.items()
                    if isinstance(values, list) and all(isinstance(value, str) for value in values)
                }
                if isinstance(data, dict)
                else {}
            )
        except (OSError, ValueError):
            return {}

    def record_consolidated_chunks(self, target_date: date, chunks: list[str]) -> None:
        """Advance only after the episode write succeeds; raw inputs stay intact."""
        from core.memory.io import atomic_write_text

        checkpoint = self._load_episode_checkpoint()
        key = target_date.isoformat()
        checkpoint[key] = sorted(
            set(checkpoint.get(key, [])) | {hashlib.sha256(chunk.encode()).hexdigest() for chunk in chunks}
        )
        atomic_write_text(
            self.anima_dir / "state" / "consolidation_episode_checkpoint.json",
            json.dumps(checkpoint, ensure_ascii=False),
        )

    @staticmethod
    def local_day_window(target_date: date, reference: datetime | None = None) -> tuple[datetime, datetime]:
        """Return local midnight bounds for *target_date*."""
        now = reference or now_local()
        timezone = now.tzinfo or get_app_timezone()
        start = datetime.combine(target_date, time.min, tzinfo=timezone)
        return start, start + timedelta(days=1)

    @staticmethod
    def previous_local_day_window(reference: datetime | None = None) -> tuple[date, datetime, datetime]:
        """Return the previous local date and its inclusive/exclusive bounds."""
        now = reference or now_local()
        if now.tzinfo is None:
            now = now.replace(tzinfo=get_app_timezone())
        target_date = now.date() - timedelta(days=1)
        start, end = ConsolidationEngine.local_day_window(target_date, now)
        return target_date, start, end

    def episode_path_for_date(self, target_date: date) -> Path:
        """Return the canonical episode file path for a local date."""
        return self.episodes_dir / f"{target_date.isoformat()}.md"

    def read_episode_for_date(self, target_date: date) -> str:
        """Read a daily episode file if it exists."""
        path = self.episode_path_for_date(target_date)
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Failed to read existing episode file %s", path, exc_info=True)
            return ""

    @classmethod
    def build_merged_episode_content(cls, existing: str, consolidated_timeline: str) -> str:
        """Preserve existing notes and append the newly consolidated timeline."""
        timeline = consolidated_timeline.strip()
        if not timeline:
            return existing

        existing = existing.strip()
        if not existing:
            return timeline + "\n"

        return f"{cls.RAW_NOTES_HEADER}\n\n{existing}\n\n{cls.CONSOLIDATED_TIMELINE_HEADER}\n\n{timeline}\n"

    def archive_episode_before_write(self, episode_path: Path) -> Path | None:
        """Copy an existing episode file to archive/episodes before overwriting it."""
        from core.memory.io import archive_episode_before_write

        return archive_episode_before_write(self.anima_dir, episode_path)

    def write_consolidated_episode(self, target_date: date, consolidated_timeline: str) -> Path:
        """Merge a consolidated timeline into the target daily episode file."""
        from core.memory.io import atomic_write_text
        from core.platform.locks import locked_path

        episode_path = self.episode_path_for_date(target_date)
        lock_path = episode_path.with_name(f"{episode_path.name}.lock")
        with locked_path(lock_path, exclusive=True, thread_lock=True):
            existing = self.read_episode_for_date(target_date)
            merged = self.build_merged_episode_content(existing, consolidated_timeline)
            if episode_path.exists():
                self.archive_episode_before_write(episode_path)
            atomic_write_text(episode_path, merged)
        return episode_path

    # ── Episode Collection ─────────────────────────────────────

    def _collect_recent_episodes(self, hours: int = 24) -> list[dict[str, str]]:
        """Collect episode entries from the past N hours.

        Supports both standard (YYYY-MM-DD.md) and suffixed
        (YYYY-MM-DD_xxx.md) episode filenames.  Files without
        ``## HH:MM — Title`` headers are treated as single entries
        using the file's mtime for timestamp.

        Args:
            hours: Number of hours to look back

        Returns:
            List of episode entries, each with 'date', 'time', 'content'
        """
        cutoff = now_local() - timedelta(hours=hours)
        entries: list[dict[str, str]] = []

        # Check today and yesterday's episode files
        for day_offset in range(2):
            target_date = now_local().date() - timedelta(days=day_offset)
            episode_files = sorted(self.episodes_dir.glob(f"{target_date}*.md"))

            for episode_file in episode_files:
                try:
                    content = episode_file.read_text(encoding="utf-8")
                except OSError:
                    logger.warning("Failed to read episode file %s", episode_file, exc_info=True)
                    continue

                # Parse episode entries (format: ## HH:MM — Title)
                found_entries = list(
                    re.finditer(
                        r"^## (\d{2}:\d{2})\s*—\s*(.+?)(?=^##|\Z)",
                        content,
                        re.MULTILINE | re.DOTALL,
                    )
                )

                if found_entries:
                    for match in found_entries:
                        time_str = match.group(1)
                        entry_content = match.group(2).strip()

                        # Parse timestamp
                        try:
                            entry_dt = ensure_aware(
                                datetime.strptime(
                                    f"{target_date} {time_str}",
                                    "%Y-%m-%d %H:%M",
                                )
                            )

                            # Only include if within time window
                            if entry_dt >= cutoff:
                                entries.append(
                                    {
                                        "date": str(target_date),
                                        "time": time_str,
                                        "content": entry_content,
                                    }
                                )
                        except ValueError:
                            logger.warning(
                                "Failed to parse episode timestamp: %s %s",
                                target_date,
                                time_str,
                            )
                else:
                    # Fallback: treat entire file as a single entry using mtime
                    file_mtime = ensure_aware(
                        datetime.fromtimestamp(
                            episode_file.stat().st_mtime,
                        )
                    )
                    if file_mtime >= cutoff:
                        entries.append(
                            {
                                "date": str(target_date),
                                "time": file_mtime.strftime("%H:%M"),
                                "content": content.strip(),
                            }
                        )

        # Deduplicate by content prefix (first 200 chars)
        seen: set[str] = set()
        unique_entries: list[dict[str, str]] = []
        for entry in entries:
            dedup_key = entry["content"][:200].strip()
            if dedup_key not in seen:
                seen.add(dedup_key)
                unique_entries.append(entry)
        entries = unique_entries

        # Sort by datetime (newest first)
        entries.sort(
            key=lambda e: datetime.strptime(f"{e['date']} {e['time']}", "%Y-%m-%d %H:%M"),
            reverse=True,
        )

        return entries

    # ── Activity Log Collection ──────────────────────────────────

    _EXCLUDED_TOOL_NAMES = frozenset(
        {
            "read_memory_file",
            "search_memory",
            "ToolSearch",
        }
    )
    _EXCLUDED_TOOL_PREFIXES = ("mcp__aw__",)

    _OVERHEAD_TOKENS = 25_000  # system prompt + template overhead
    _CONTEXT_RATIO = 0.80
    _CHARS_PER_TOKEN = 3

    # ── Activity log budget & full collection ───────────────────

    @staticmethod
    def compute_activity_budget(model: str) -> int:
        """Compute character budget for activity log based on model context window.

        Uses 80% of context window minus overhead for prompt templates.
        """
        from core.prompt.context import resolve_context_window

        ctx = resolve_context_window(model)
        budget_tokens = int(ctx * ConsolidationEngine._CONTEXT_RATIO)
        available = max(budget_tokens - ConsolidationEngine._OVERHEAD_TOKENS, 10_000)
        return available * ConsolidationEngine._CHARS_PER_TOKEN

    @staticmethod
    def _is_excluded_tool(entry: Any) -> bool:
        """Check if a tool_result/tool_use entry should be excluded."""
        tool = getattr(entry, "tool", None) or ""
        if tool in ConsolidationEngine._EXCLUDED_TOOL_NAMES:
            return True
        return any(tool.startswith(prefix) for prefix in ConsolidationEngine._EXCLUDED_TOOL_PREFIXES)

    @staticmethod
    def _truncate_utf8(text: str, max_bytes: int) -> str:
        """Truncate untrusted activity payload text without splitting UTF-8."""
        if len(text.encode("utf-8")) <= max_bytes:
            return text
        marker = "\n... (truncated)"
        marker_bytes = marker.encode("utf-8")
        if max_bytes <= len(marker_bytes):
            return marker_bytes[:max_bytes].decode("utf-8", errors="ignore")
        head = text.encode("utf-8")[: max_bytes - len(marker_bytes)].decode("utf-8", errors="ignore")
        return head + marker

    @staticmethod
    def _format_entry_full(entry: Any, *, max_content_bytes: int = 64 * 1024) -> str:
        """Format activity content for consolidation, clipping large raw payloads.

        This includes the actual content of tool results, messages, etc., but
        applies a byte cap before a pasted message or tool result reaches an LLM.
        """
        ts_short = entry.ts[11:16] if len(entry.ts) >= 16 else entry.ts
        meta = entry.meta or {}

        # Build context parts
        parts: list[str] = []
        if entry.from_person:
            parts.append(f"from:{entry.from_person}")
        if entry.to_person:
            parts.append(f"to:{entry.to_person}")
        if entry.channel:
            parts.append(f"#{entry.channel}")
        ctx = f" ({', '.join(parts)})" if parts else ""

        type_labels = {
            "message_received": "MSG_IN",
            "response_sent": "RESPONSE",
            "message_sent": "MSG_OUT",
            "human_notify": "NOTIFY",
            "heartbeat_reflection": "HB_REFLECT",
            "channel_post": "CHANNEL",
            "error": "ERROR",
            "tool_result": "TOOL_RESULT",
            "tool_use": "TOOL_USE",
            "cron_executed": "CRON",
            "memory_write": "MEM_WRITE",
            "heartbeat_start": "HB_START",
            "heartbeat_end": "HB_END",
            "consolidation_start": "CONSOL_START",
            "consolidation_end": "CONSOL_END",
        }
        label = type_labels.get(entry.type, entry.type.upper())

        # For tool entries, include tool name
        tool_name = entry.tool or ""
        if tool_name and entry.type in ("tool_result", "tool_use"):
            label = f"{label}:{tool_name}"

        # Build status suffix for tool_result
        status_suffix = ""
        if entry.type == "tool_result":
            status = meta.get("result_status", "ok")
            if status == "fail":
                status_suffix = " [FAIL]"

        # Content: prefer summary for brief context, fall back to content
        summary = entry.summary or ""
        content = entry.content or ""

        # For tool_result, content is the actual result — include it
        if entry.type == "tool_result" and content:
            text = content
        elif summary and content:
            text = f"{summary}\n{content}" if len(summary) < 200 else summary
        elif summary:
            text = summary
        elif content:
            text = content
        else:
            text = "(no content)"

        text = ConsolidationEngine._truncate_utf8(text, max_content_bytes)
        header = f"[{ts_short}] {label}{status_suffix}{ctx}"

        # If text is short, put on same line
        if len(text) <= 200 and "\n" not in text:
            return f"{header}: {text}"

        # For longer content, use indented block
        indented = "\n".join(f"  {line}" for line in text.split("\n"))
        return f"{header}:\n{indented}"

    def count_recent_activity_entries(
        self,
        hours: int = 24,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Count activity-log entries eligible for daily consolidation."""
        try:
            from core.activity.logger import ActivityLogger

            activity = ActivityLogger(self.anima_dir)
            if since is not None or until is not None:
                entries = activity._load_entries(since=since, until=until)
            else:
                entries = activity.recent(
                    days=max(1, (hours + 23) // 24),
                    limit=10_000,
                )
        except Exception:
            logger.debug("Failed to count activity entries", exc_info=True)
            return 0

        cutoff = None if since is not None or until is not None else now_local() - timedelta(hours=hours)
        count = 0
        for entry in entries:
            if entry.type in ("tool_result", "tool_use") and self._is_excluded_tool(entry):
                continue
            try:
                ts = ensure_aware(datetime.fromisoformat(entry.ts))
                if since is not None and ts < since:
                    continue
                if until is not None and ts >= until:
                    continue
                if cutoff is not None and ts < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
            count += 1
        return count

    def collect_activity_chunks(
        self,
        hours: int = 24,
        model: str | None = None,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        max_input_bytes: int = 200 * 1024,
    ) -> list[str]:
        """Collect activity entries and split into budget-sized chunks.

        Returns a list of formatted text chunks, each within the model's
        budget. Chunks are split at natural hour boundaries when possible.

        Args:
            hours: Number of hours to look back.
            model: Model name for budget calculation. Uses consolidation
                model from config if not provided.
            since: Optional inclusive lower timestamp bound. When provided,
                it takes precedence over ``hours`` for entry filtering.
            until: Optional exclusive upper timestamp bound, used with
                ``since`` for fixed date windows.

        Returns:
            List of formatted activity text chunks. Empty list if no entries.
        """
        if model is None:
            from core.config import load_config

            cfg = load_config()
            model = cfg.consolidation.llm_model

        # Keep chunk boundaries stable so existing checkpoint hashes remain valid;
        # oversized rendered prompts are split immediately before the LLM call.
        budget = self.compute_activity_budget(model)
        entry_content_bytes = min(64 * 1024, max(256, max_input_bytes // 2))

        try:
            from core.activity.logger import ActivityLogger

            activity = ActivityLogger(self.anima_dir)

            if since is not None or until is not None:
                entries = activity._load_entries(since=since, until=until)
            else:
                # Load all entries (no type filter, high limit)
                entries = activity.recent(
                    days=max(1, (hours + 23) // 24),
                    limit=10_000,
                )
        except Exception:
            logger.debug("Failed to collect activity entries", exc_info=True)
            return []

        if not entries:
            return []

        cutoff = None if since is not None or until is not None else now_local() - timedelta(hours=hours)
        filtered: list = []
        for e in entries:
            try:
                ts = ensure_aware(datetime.fromisoformat(e.ts))
                if since is not None and ts < since:
                    continue
                if until is not None and ts >= until:
                    continue
                if since is not None or until is not None:
                    filtered.append(e)
                    continue
                if cutoff is not None and ts >= cutoff:
                    filtered.append(e)
            except (ValueError, TypeError):
                if since is None and until is None:
                    filtered.append(e)

        if not filtered:
            return []

        # Apply exclusion list
        included: list = []
        for e in filtered:
            if e.type in ("tool_result", "tool_use") and self._is_excluded_tool(e):
                continue
            # Skip tool_use for mcp__aw__ (duplicate with tool_result)
            if e.type == "tool_use":
                tool = getattr(e, "tool", None) or ""
                for prefix in self._EXCLUDED_TOOL_PREFIXES:
                    if tool.startswith(prefix):
                        break
                else:
                    included.append(e)
                continue
            included.append(e)

        if not included:
            return []

        # Format all entries — use date+hour key for cross-day correctness
        formatted_entries: list[tuple[str, str]] = []  # (date_hour_key, formatted_text)
        for e in included:
            text = self._format_entry_full(e, max_content_bytes=entry_content_bytes)
            date_hour = e.ts[:13] if len(e.ts) >= 13 else "0000-00-00T00"
            formatted_entries.append((date_hour, text))

        # Split into budget-sized chunks at hour boundaries
        return self._split_into_chunks(formatted_entries, budget)

    @staticmethod
    def _split_into_chunks(
        entries: list[tuple[str, str]],
        budget: int,
    ) -> list[str]:
        """Split formatted entries into budget-sized chunks.

        Tries to break at hour boundaries for natural segmentation.
        """
        if not entries:
            return []

        chunks: list[str] = []
        current_lines: list[str] = []
        current_size = 0
        current_hour = entries[0][0]

        # Buffer for entries in the current hour
        hour_buffer: list[str] = []
        hour_buffer_size = 0

        for hour_key, text in entries:
            entry_size = len(text) + 1  # +1 for newline

            if hour_key != current_hour:
                # Hour boundary — check if we should start a new chunk
                if current_size + hour_buffer_size > budget and current_lines:
                    # Flush current chunk, start new one with buffer
                    chunks.append("\n".join(current_lines))
                    current_lines = list(hour_buffer)
                    current_size = hour_buffer_size
                else:
                    # Add buffer to current chunk
                    current_lines.extend(hour_buffer)
                    current_size += hour_buffer_size

                hour_buffer = []
                hour_buffer_size = 0
                current_hour = hour_key

            # If single entry exceeds budget, truncate it
            if entry_size > budget:
                text = text[: budget - 100] + "\n  ... (truncated)"
                entry_size = len(text) + 1

            hour_buffer.append(text)
            hour_buffer_size += entry_size

        # Flush remaining hour buffer
        if current_size + hour_buffer_size > budget and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = list(hour_buffer)
        else:
            current_lines.extend(hour_buffer)

        if current_lines:
            chunks.append("\n".join(current_lines))

        return chunks

    async def extract_facts_from_text_outcome(
        self,
        text: str,
        *,
        source_episode: str,
        source_session_id: str = "consolidation:daily",
    ):
        """Extract/store atomic facts and return operational counters.

        Long text is split into chunks of at most ``fact_extraction_chunk_chars``
        characters (set ``0`` to disable) and each chunk is processed
        sequentially. A failing chunk does not stop the rest; the number of
        failed chunks is surfaced via ``failed_chunks`` (and ``facts_failed``).
        """
        try:
            from core.config import load_config
            from core.memory.facts.chunking import split_text_for_fact_extraction
            from core.memory.facts.extraction import (
                FactExtractionOutcome,
                extract_and_store_facts_with_outcome,
            )

            cfg = load_config()
            max_chars = int(getattr(cfg.consolidation, "fact_extraction_chunk_chars", 12000) or 0)
            chunks = split_text_for_fact_extraction(text, max_chars)
            total_chunks = len(chunks)

            all_records: list = []
            failed = False
            failure_stage = ""
            failure_reason = ""
            failed_chunks = 0

            for i, chunk in enumerate(chunks, start=1):
                try:
                    outcome = await extract_and_store_facts_with_outcome(
                        self.anima_dir,
                        chunk,
                        source_episode=source_episode,
                        source_session_id=source_session_id,
                        origin="consolidation",
                    )
                except Exception as exc:  # noqa: BLE001 - keep processing other chunks
                    failed = True
                    failed_chunks += 1
                    reason = f"{type(exc).__name__}: {exc}"
                    if not failure_stage:
                        failure_stage = "chunk"
                    if not failure_reason:
                        failure_reason = f"chunk {i}/{total_chunks}: {reason}"
                    logger.warning(
                        "Fact extraction chunk failed anima=%s chunk=%d/%d stage=%s reason=%s",
                        self.anima_name,
                        i,
                        total_chunks,
                        "chunk",
                        reason[:300],
                    )
                    continue

                all_records.extend(outcome.records)
                if outcome.failed:
                    failed = True
                    failed_chunks += 1
                    if not failure_stage:
                        failure_stage = outcome.failure_stage or "chunk"
                    if not failure_reason:
                        failure_reason = f"chunk {i}/{total_chunks}: {outcome.failure_reason or 'failed'}"
                    logger.warning(
                        "Fact extraction chunk failed anima=%s chunk=%d/%d stage=%s reason=%s",
                        self.anima_name,
                        i,
                        total_chunks,
                        outcome.failure_stage or "chunk",
                        (outcome.failure_reason or "failed")[:300],
                    )

            outcome = FactExtractionOutcome(
                records=all_records,
                failed=failed,
                failure_stage=failure_stage,
                failure_reason=failure_reason,
                failed_chunks=failed_chunks,
                total_chunks=total_chunks,
            )
            first_failure = f" first_failure={failure_reason[:300].replace(chr(10), ' ')}" if failed else ""
            logger.info(
                (
                    "Consolidation atomic fact extraction complete for anima=%s: "
                    "facts_extracted=%d facts_failed=%d chunks=%d%s"
                ),
                self.anima_name,
                outcome.facts_extracted,
                outcome.facts_failed,
                outcome.total_chunks,
                first_failure,
            )
            return outcome
        except Exception as exc:
            from core.memory.facts.extraction import FactExtractionOutcome
            from core.memory.facts.observability import warn_rate_limited

            warn_rate_limited(
                logger,
                "fact_extraction.consolidation",
                "Consolidation atomic fact extraction failed for anima=%s",
                self.anima_name,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            reason = f"{type(exc).__name__}: {exc}"
            logger.info(
                (
                    "Consolidation atomic fact extraction complete for anima=%s: "
                    "facts_extracted=0 facts_failed=1 chunks=1 first_failure=%s"
                ),
                self.anima_name,
                reason[:300].replace(chr(10), " "),
            )
            return FactExtractionOutcome([], True, "consolidation", reason, failed_chunks=1, total_chunks=1)

    @staticmethod
    def merge_timeline_parts(parts: list[str]) -> str:
        """Merge multiple structured timeline parts into a single episode.

        Concatenates timeline parts in order, deduplicating any repeated
        section headers (## HH:MM-HH:MM Title) that might appear at
        chunk boundaries.
        """
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]

        seen_headers: set[str] = set()
        merged_lines: list[str] = []

        for part in parts:
            for line in part.split("\n"):
                # Detect markdown ## headers for dedup
                stripped = line.strip()
                if stripped.startswith("## "):
                    if stripped in seen_headers:
                        continue
                    seen_headers.add(stripped)
                merged_lines.append(line)

        return "\n".join(merged_lines)

    # ── Utilities ────────────────────────────────────────────────

    @staticmethod
    def _sanitize_llm_output(text: str) -> str:
        """Remove code fences from LLM output.

        LLMs sometimes wrap their entire response in ```markdown fences.
        This method strips those wrapper fences while preserving any
        intentional code blocks within the content.

        Args:
            text: Raw LLM output

        Returns:
            Cleaned text with wrapper code fences removed.
        """
        from core.memory._llm_parse import strip_code_fence

        return strip_code_fence(text)

    @staticmethod
    def _is_archive_dir(rel: Path) -> bool:
        """Check if a path is inside an archive subdirectory.

        Handles all known archive directory naming conventions:
        ``archive/``, ``_archived/``, ``.archive/``.
        """
        if not rel.parts:
            return False
        first = rel.parts[0].lower().lstrip("_").lstrip(".")
        return first == "archive" or first == "archived"

    # ── Merge Candidate Detection ─────────────────────────────────

    def _find_merge_candidates(
        self,
        similarity_threshold: float = 0.75,
        max_pairs: int = 20,
    ) -> list[tuple[str, str, float]]:
        """Find knowledge file pairs that are candidates for merging.

        Uses RAG vector similarity to detect semantically similar files.
        All knowledge files are eligible (no low-activation requirement).
        Files in archive/ subdirectories are excluded.

        Args:
            similarity_threshold: Minimum vector similarity for a pair (0.0-1.0).
            max_pairs: Maximum number of pairs to return.

        Returns:
            List of (file_a, file_b, similarity) tuples, sorted by
            similarity descending.  Paths are relative to knowledge/.
        """
        # Read all non-archived knowledge files
        from core.memory.frontmatter import parse_frontmatter

        file_contents: dict[str, str] = {}
        for path in sorted(self.knowledge_dir.rglob("*.md")):
            rel = path.relative_to(self.knowledge_dir)
            if self._is_archive_dir(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
                _, body = parse_frontmatter(text)
                if body.strip():
                    file_contents[str(rel)] = body.strip()
            except Exception:
                continue

        if len(file_contents) < 2:
            return []

        try:
            from core.memory.rag import MemoryIndexer
            from core.memory.rag.retriever import MemoryRetriever
            from core.memory.rag.vector_registry import get_vector_store

            vector_store = self._rag_store or get_vector_store(self.anima_name)
            if vector_store is None:
                logger.debug("RAG vector store unavailable for merge candidate search")
                return []
            indexer = MemoryIndexer(vector_store, self.anima_name, self.anima_dir)
            retriever = MemoryRetriever(vector_store, indexer, self.knowledge_dir)
        except (ImportError, Exception) as exc:
            logger.debug("RAG not available for merge candidate search: %s", exc)
            return []

        # Query each file against RAG to find similar peers
        seen_pairs: set[tuple[str, str]] = set()
        candidates: list[tuple[str, str, float]] = []

        for rel_path, content in file_contents.items():
            try:
                results = retriever.search(
                    query=content[:500],
                    anima_name=self.anima_name,
                    memory_type="knowledge",
                    top_k=5,
                )
            except Exception:
                continue

            for result in results:
                raw_sim = getattr(result, "source_scores", {}).get("vector", result.score)
                if raw_sim < similarity_threshold:
                    continue

                source_file = str(result.metadata.get("source_file", ""))
                if not source_file:
                    continue

                # Normalise to relative path under knowledge/
                if source_file.startswith("knowledge/"):
                    match_rel = source_file[len("knowledge/") :]
                elif source_file.startswith("knowledge\\"):
                    match_rel = source_file[len("knowledge\\") :]
                else:
                    match_rel = source_file

                match_rel_path = Path(match_rel)
                if match_rel == rel_path:
                    continue
                if self._is_archive_dir(match_rel_path):
                    continue
                # Skip if the matched file isn't in our content map
                if match_rel not in file_contents:
                    continue

                pair_key = tuple(sorted([rel_path, match_rel]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                candidates.append((rel_path, match_rel, raw_sim))

        # Sort by similarity descending, cap at max_pairs
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[:max_pairs]

    # ── Conflicting-fact candidates ────────────────────────────

    def _find_conflicting_fact_candidates(
        self,
        max_pairs: int = 20,
    ) -> list[tuple[str, str, str]]:
        """Find conflicting fact pairs for the weekly consolidation LLM.

        Reads the legacy atomic facts stored as JSONL under ``{anima_dir}/facts/``.
        Facts are grouped by entity (``source_entity``) + attribute
        (``target_entity`` / ``edge_type``).  When two currently-active facts in
        the same group describe different values (``text``), the pair is a
        candidate for the weekly consolidation model to resolve (archive the
        older one or report unresolved).

        Only active facts (no valid_until, or valid_until still in the future)
        are considered, so superseded/expired records do not surface as
        conflicts.

        Args:
            max_pairs: Maximum number of pairs to return.

        Returns:
            List of (older_fact_path, newer_fact_path, one_line_description)
            sorted by the newer fact's observed time (newest first).  Paths are
            relative to the anima_dir and include the JSONL file and fact id so
            the model can locate the exact record.
        """
        from core.memory.facts.store import FactRecord, facts_dir

        facts_dir_path = facts_dir(self.anima_dir)
        if not facts_dir_path.exists():
            return []

        # Group by (source_entity, target_entity, edge_type).
        grouped: dict[tuple[str, str, str], list[dict]] = {}
        for jsonl in sorted(facts_dir_path.glob("*.jsonl")):
            try:
                lines = jsonl.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = FactRecord.from_json_line(line)
                except Exception:
                    continue
                if not record.is_active():
                    continue
                entity = (record.source_entity, record.target_entity, record.edge_type)
                observed = record.recorded_at or record.valid_at or ""
                grouped.setdefault(entity, []).append(
                    {
                        "path": f"{jsonl.relative_to(self.anima_dir).as_posix()}#{record.fact_id}",
                        "text": record.text,
                        "observed": observed,
                    }
                )

        # (older_path, newer_path, description, newer_observed)
        raw: list[tuple[str, str, str, str]] = []
        for items in grouped.values():
            if len(items) < 2:
                continue
            # Newest item is compared against every older item with a
            # different value (source of the conflict).
            items_sorted = sorted(items, key=lambda i: i["observed"], reverse=True)
            newest = items_sorted[0]
            for older in items_sorted[1:]:
                if older["text"] == newest["text"]:
                    continue
                raw.append(
                    (
                        older["path"],
                        newest["path"],
                        (
                            f"{newest['text'][:60]!r} (recent) differs from "
                            f"{older['text'][:60]!r} (earlier) for the same attribute"
                        ),
                        newest["observed"],
                    )
                )

        raw.sort(key=lambda c: c[3], reverse=True)
        return [(a, b, d) for a, b, d, _ in raw[:max_pairs]]
