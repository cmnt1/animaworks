from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Active forgetting mechanism based on synaptic homeostasis hypothesis.

Implements two stages of memory forgetting:
1. Synaptic downscaling (daily): Mark low-activation chunks
2. Forgetting candidates (weekly): List low-activation chunks for the model to review

Mechanical deletion/archival was removed (harness diet PR-7): the weekly
consolidation now shows candidates to the model, which decides via the
``archive_memory_file`` tool.

Based on:
- Tononi & Cirelli (2003, 2006): Synaptic homeostasis hypothesis
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.time_utils import ensure_aware, now_local

logger = logging.getLogger("animaworks.forgetting")

# ── Configuration ──────────────────────────────────────────────────

# Synaptic downscaling thresholds
DOWNSCALING_DAYS_THRESHOLD = 90  # Days since last access
DOWNSCALING_ACCESS_THRESHOLD = 3  # Minimum access count to avoid marking

# Complete forgetting
FORGETTING_LOW_ACTIVATION_DAYS = 90  # Days in low activation before deletion
FORGETTING_MAX_ACCESS_COUNT = 2  # Max access count to still be eligible for deletion

# Protected memory types (skills and shared_users are fully protected)
PROTECTED_MEMORY_TYPES = frozenset({"skills", "shared_users"})

# [IMPORTANT] safety net: after this many days without access,
# important chunks lose protection (conceptual integration should
# have happened by then via weekly consolidation prompts).
IMPORTANT_SAFETY_NET_DAYS = 365

# Procedure-specific forgetting thresholds (more lenient than knowledge)
PROCEDURE_INACTIVITY_DAYS = 180  # Days since last use (vs 90 for knowledge)
PROCEDURE_MIN_USAGE = 3  # Minimum total usage to avoid downscaling
PROCEDURE_LOW_UTILITY_THRESHOLD = 0.3  # Utility score below this is low
PROCEDURE_LOW_UTILITY_MIN_FAILURES = 3  # Min failures for utility check
PROCEDURE_ARCHIVE_KEEP_VERSIONS = 5  # Keep N most recent archive versions

# ── ForgettingCandidate ────────────────────────────────────────────


@dataclass
class ForgettingCandidate:
    """A single forgetting candidate shown to the model for review.

    Attributes:
        path: Relative path (passable to ``read_memory_file``).
        days_low: Days the memory has been in low activation (integer).
        used_count: Total usage count (explicit uses + auto recalls).
        last_used_at: Most recent usage timestamp or empty string.
        reason: Short one-line human-readable explanation.
    """

    path: str
    days_low: int
    used_count: int
    last_used_at: str
    reason: str


# ── ForgettingEngine ───────────────────────────────────────────────


class ForgettingEngine:
    """Active forgetting based on synaptic homeostasis."""

    def __init__(self, anima_dir: Path, anima_name: str) -> None:
        self.anima_dir = anima_dir
        self.anima_name = anima_name
        self.archive_dir = anima_dir / "archive" / "forgotten"

    def _is_protected(self, metadata: dict) -> bool:
        """Check if a chunk is protected from forgetting.

        Fully protected types (skills, shared_users) are always skipped.
        Procedures use utility-based protection via ``_is_protected_procedure``.
        Knowledge with ``success_count >= 2`` is protected via
        ``_is_protected_knowledge``.
        The ``importance == "important"`` tag protects any memory type,
        but with a safety-net: chunks that remain unaccessed for
        ``IMPORTANT_SAFETY_NET_DAYS`` lose their protection (conceptual
        integration via weekly consolidation should have happened by then).
        """
        if metadata.get("memory_type") in PROTECTED_MEMORY_TYPES:
            return True
        important_expired = False
        if metadata.get("importance") == "important":
            important_expired = self._important_safety_net_expired(metadata)
            if not important_expired:
                return True
        # Procedures use utility-based protection instead of blanket protection
        if metadata.get("memory_type") == "procedures":
            return self._is_protected_procedure(metadata, important_expired=important_expired)
        # Knowledge with confirmed usefulness is protected
        if metadata.get("memory_type") == "knowledge":
            return self._is_protected_knowledge(metadata, important_expired=important_expired)
        return False

    def _important_safety_net_expired(self, metadata: dict) -> bool:
        """Check if an [IMPORTANT] chunk has exceeded the safety-net window.

        Returns True when the chunk has gone unaccessed for longer than
        ``IMPORTANT_SAFETY_NET_DAYS``, meaning conceptual integration
        should have occurred by now and the raw episodic [IMPORTANT]
        can safely enter normal forgetting.
        """
        used_count = self._used_count(metadata)
        if used_count > 0:
            last_used_str = self._last_used_at(metadata)
            if last_used_str:
                try:
                    last_dt = ensure_aware(datetime.fromisoformat(str(last_used_str)))
                    days = (now_local() - last_dt).total_seconds() / 86400.0
                    return days > IMPORTANT_SAFETY_NET_DAYS
                except (ValueError, TypeError):
                    pass
            return False

        updated_str = metadata.get("updated_at", "")
        if updated_str:
            try:
                updated_dt = ensure_aware(datetime.fromisoformat(str(updated_str)))
                days = (now_local() - updated_dt).total_seconds() / 86400.0
                return days > IMPORTANT_SAFETY_NET_DAYS
            except (ValueError, TypeError):
                pass
        return False

    @staticmethod
    def _number(metadata: dict, key: str, *, default: float = 0.0) -> float:
        try:
            return max(0.0, float(str(metadata.get(key, default))))
        except (TypeError, ValueError):
            return max(0.0, default)

    def _used_count(self, metadata: dict) -> float:
        """Return combined usage: explicit uses plus automatic recalls (F11).

        Auto-recall (``access_count``) now counts toward "usage" so memories
        that keep getting retrieved by search stay protected from forgetting,
        matching the access-boost philosophy. Legacy chunks predating the
        used/access split carry only ``access_count`` (``used_count`` absent →
        0), so the sum equals the legacy value and remains backward compatible.
        Explicit uses bump both counters, which merely over-protects (never
        under-protects) already-used memories.
        """
        return self._number(metadata, "used_count") + self._number(metadata, "access_count")

    @staticmethod
    def _last_used_at(metadata: dict) -> str:
        """Return the most recent usage timestamp (F11).

        Combines the explicit-use time (``last_used_at`` / legacy ``last_used``)
        with the automatic-recall time (``last_accessed_at``) and returns the
        latest, so a memory that keeps getting retrieved registers as recently
        used. Returns an empty string when no timestamp is present.
        """
        candidates: list[str] = []
        for key in ("last_used_at", "last_used", "last_accessed_at"):
            value = str(metadata.get(key, "") or "").strip()
            if value:
                candidates.append(value)
        if not candidates:
            return ""
        return max(candidates)

    def _is_protected_knowledge(self, metadata: dict, *, important_expired: bool = False) -> bool:
        """Knowledge-specific protection check.

        Returns True (protected) if any of:
        - ``importance == "important"`` ([IMPORTANT] tag), unless the
          top-level important safety net has expired
        - ``success_count >= 2`` (knowledge confirmed useful multiple times)

        Args:
            metadata: Chunk metadata from the vector store.

        Returns:
            True if the knowledge chunk should be protected from forgetting.
        """
        if metadata.get("importance") == "important" and not important_expired:
            return True
        if int(metadata.get("success_count", 0)) >= 2:  # noqa: SIM103
            return True
        return False

    def _is_protected_procedure(self, metadata: dict, *, important_expired: bool = False) -> bool:
        """Procedure-specific protection check.

        Returns True (protected) if any of:
        - ``importance == "important"`` ([IMPORTANT] tag), unless the
          top-level important safety net has expired
        - ``protected is True`` (manual protection flag)
        - ``version >= 3`` (mature procedure that survived reconsolidation)
        """
        if metadata.get("importance") == "important" and not important_expired:
            return True
        if metadata.get("protected") is True:
            return True
        if metadata.get("version", 1) >= 3:  # noqa: SIM103
            return True
        return False

    def _should_downscale_procedure(
        self,
        metadata: dict,
        now: datetime,
    ) -> bool:
        """Procedure-specific downscaling check.

        A procedure is marked low-activation if either:
        1. Inactive for >180 days AND total usage < 3 (rarely used, old)
        2. failure_count >= 3 AND utility score < 0.3 (high failure rate)

        Args:
            metadata: Chunk metadata from the vector store.
            now: Current datetime for age calculation.

        Returns:
            True if the procedure should be marked as low-activation.
        """
        # Calculate days since last use
        last_used_str = self._last_used_at(metadata)
        if not last_used_str:
            last_used_str = metadata.get("updated_at", "")

        if last_used_str:
            try:
                last_used_dt = ensure_aware(datetime.fromisoformat(str(last_used_str)))
                days_since = (now - last_used_dt).total_seconds() / 86400.0
            except (ValueError, TypeError):
                days_since = float("inf")
        else:
            days_since = float("inf")

        success_count = int(metadata.get("success_count", 0))
        failure_count = int(metadata.get("failure_count", 0))
        total_usage = max(success_count + failure_count, int(self._used_count(metadata)))

        # Condition 1: Long inactivity + low total usage
        if days_since > PROCEDURE_INACTIVITY_DAYS and total_usage < PROCEDURE_MIN_USAGE:
            return True

        # Condition 2: High failure rate (utility < 0.3 with >= 3 failures)
        if failure_count >= PROCEDURE_LOW_UTILITY_MIN_FAILURES:
            utility = success_count / max(1, total_usage)
            if utility < PROCEDURE_LOW_UTILITY_THRESHOLD:
                return True

        return False

    def _get_vector_store(self):
        """Get vector store singleton.

        Returns:
            VectorStore instance, or ``None`` if unavailable.
        """
        from core.memory.rag.singleton import get_vector_store

        return get_vector_store(self.anima_name)

    def _get_all_chunks(self, collection_name: str) -> list[dict]:
        """Get all chunks from a collection with their metadata."""
        try:
            store = self._get_vector_store()
            if store is None:
                return []
            results = store.get_by_metadata(collection_name, {}, limit=100_000)
            return [
                {
                    "id": r.document.id,
                    "metadata": dict(r.document.metadata),
                    "content": r.document.content,
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("Failed to get chunks from %s: %s", collection_name, e)
            return []

    # ── Stage 1: Synaptic Downscaling (Daily) ──────────────────────

    def synaptic_downscaling(self) -> dict[str, Any]:
        """Mark low-activation chunks (daily, runs in daily_consolidate).

        Criteria: days_since_access > 90 AND access_count < 3
        Action: Set activation_level="low", record low_activation_since
        Skip: Protected memory types, important chunks, already low
        """
        logger.info("Starting synaptic downscaling for anima=%s", self.anima_name)
        now = now_local()
        now_iso_str = now.isoformat()
        total_scanned = 0
        total_marked = 0
        store = self._get_vector_store()

        if store is None:
            logger.warning(
                "Skipping synaptic downscaling for anima=%s: RAG/ChromaDB unavailable",
                self.anima_name,
            )
            return {"scanned": 0, "marked_low": 0, "skipped_reason": "rag_unavailable"}

        # Scan all relevant collections (including procedures)
        for memory_type in ("knowledge", "episodes", "procedures"):
            collection_name = f"{self.anima_name}_{memory_type}"
            chunks = self._get_all_chunks(collection_name)
            total_scanned += len(chunks)

            ids_to_mark: list[str] = []
            metas_to_mark: list[dict] = []

            for chunk in chunks:
                meta = chunk["metadata"]

                # Skip protected
                if self._is_protected(meta):
                    continue

                # Skip already low
                if meta.get("activation_level") == "low":
                    continue

                # Procedure-specific downscaling logic
                if meta.get("memory_type") == "procedures":
                    if self._should_downscale_procedure(meta, now):
                        ids_to_mark.append(chunk["id"])
                        metas_to_mark.append(
                            {
                                "activation_level": "low",
                                "low_activation_since": now_iso_str,
                            }
                        )
                    continue

                # Check access recency
                used_count = self._used_count(meta)
                last_used_str = self._last_used_at(meta)

                if last_used_str:
                    try:
                        last_used = ensure_aware(datetime.fromisoformat(str(last_used_str)))
                        days_since = (now - last_used).total_seconds() / 86400.0
                    except (ValueError, TypeError):
                        days_since = float("inf")
                else:
                    # Never used — use updated_at as fallback
                    updated_str = meta.get("updated_at", "")
                    if updated_str:
                        try:
                            updated_at = ensure_aware(datetime.fromisoformat(str(updated_str)))
                            days_since = (now - updated_at).total_seconds() / 86400.0
                        except (ValueError, TypeError):
                            days_since = float("inf")
                    else:
                        days_since = float("inf")

                # Apply threshold
                if days_since > DOWNSCALING_DAYS_THRESHOLD and used_count < DOWNSCALING_ACCESS_THRESHOLD:
                    ids_to_mark.append(chunk["id"])
                    metas_to_mark.append(
                        {
                            "activation_level": "low",
                            "low_activation_since": now_iso_str,
                        }
                    )

            # Batch update
            if ids_to_mark:
                try:
                    store.update_metadata(collection_name, ids_to_mark, metas_to_mark)
                    total_marked += len(ids_to_mark)
                    logger.info(
                        "Marked %d chunks as low-activation in %s",
                        len(ids_to_mark),
                        collection_name,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to mark chunks in %s: %s",
                        collection_name,
                        e,
                    )

        result = {
            "scanned": total_scanned,
            "marked_low": total_marked,
        }
        logger.info(
            "Synaptic downscaling complete for anima=%s: scanned=%d, marked=%d",
            self.anima_name,
            total_scanned,
            total_marked,
        )
        logger.info(
            "forgetting_funnel: anima=%s stage=downscaling scanned=%d marked=%d merged=0 forgotten=0",
            self.anima_name,
            total_scanned,
            total_marked,
        )
        return result

    # ── Stage 2: Forgetting Candidates (weekly, model-driven) ───────

    def list_forgetting_candidates(self, max_items: int = 20) -> list[ForgettingCandidate]:
        """Return low-activation memory candidates for the model to review.

        Uses the same eligibility criteria as the former mechanical forgetting
        (low activation for ``FORGETTING_LOW_ACTIVATION_DAYS`` with usage
        ``<= FORGETTING_MAX_ACCESS_COUNT``, honoring protection rules).  It only
        **lists** candidates (sorted by low-activation days, descending) and does
        NOT delete from the index or move files; the model decides via the
        ``archive_memory_file`` tool during weekly consolidation.

        Chunks sharing the same source file are collapsed into a single
        candidate.  Returns an empty list when RAG is unavailable.
        """
        store = self._get_vector_store()
        if store is None:
            logger.warning(
                "Skipping forgetting candidate scan for anima=%s: RAG/ChromaDB unavailable",
                self.anima_name,
            )
            return []

        now = now_local()
        # source_file -> candidate accumulator (highest days_low wins)
        grouped: dict[str, ForgettingCandidate] = {}

        for memory_type in ("knowledge", "episodes", "procedures"):
            collection_name = f"{self.anima_name}_{memory_type}"
            for chunk in self._get_all_chunks(collection_name):
                meta = chunk["metadata"]

                # Skip protected
                if self._is_protected(meta):
                    continue

                # Must be low activation
                if meta.get("activation_level") != "low":
                    continue

                # Check duration of low activation
                low_since_str = meta.get("low_activation_since", "")
                if not low_since_str:
                    continue
                try:
                    low_since = ensure_aware(datetime.fromisoformat(str(low_since_str)))
                    days_low = int((now - low_since).total_seconds() / 86400.0)
                except (ValueError, TypeError):
                    continue

                # Check eligibility criteria
                used_count = int(self._used_count(meta))
                if not (days_low > FORGETTING_LOW_ACTIVATION_DAYS and used_count <= FORGETTING_MAX_ACCESS_COUNT):
                    continue

                source_file = meta.get("source_file", "")
                if not source_file or source_file == "merged":
                    continue

                existing = grouped.get(source_file)
                if existing is None or days_low > existing.days_low:
                    grouped[source_file] = ForgettingCandidate(
                        path=source_file,
                        days_low=days_low,
                        used_count=used_count,
                        last_used_at=self._last_used_at(meta),
                        reason=f"{days_low}日間低活性・参照{used_count}回",
                    )

        candidates = sorted(grouped.values(), key=lambda c: c.days_low, reverse=True)
        logger.info(
            "Forgetting candidates for anima=%s: found=%d (max_items=%d)",
            self.anima_name,
            len(candidates),
            max_items,
        )
        return candidates[:max_items]
