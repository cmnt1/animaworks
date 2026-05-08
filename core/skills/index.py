from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Metadata index over personal skills, common skills, and procedures."""

import logging
from datetime import datetime
from pathlib import Path

from core.skills.loader import load_skill_metadata
from core.skills.models import SkillMetadata, SkillTrustLevel

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────

_EXCLUDED_TRUST_LEVELS: frozenset[SkillTrustLevel] = frozenset({SkillTrustLevel.blocked, SkillTrustLevel.quarantine})


# ── SkillIndex ────────────────────────────────────────────


class SkillIndex:
    """Scan skill and procedure directories and query metadata."""

    def __init__(
        self,
        skills_dir: Path,
        common_skills_dir: Path,
        procedures_dir: Path | None = None,
        *,
        anima_dir: Path | None = None,
    ) -> None:
        """Initialize index roots.

        Args:
            skills_dir: Directory containing per-Anima skill folders with ``SKILL.md``.
            common_skills_dir: Directory containing shared skill folders (flat or nested).
            procedures_dir: Optional directory of procedure ``*.md`` files; ``None`` skips.
            anima_dir: Optional anima directory for usage stats integration.
        """
        self._skills_dir = skills_dir
        self._common_skills_dir = common_skills_dir
        self._procedures_dir = procedures_dir
        self._anima_dir = anima_dir
        self._cached_index: list[SkillMetadata] | None = None
        self._cached_all_entries: list[SkillMetadata] | None = None

    # ── Cache ───────────────────────────────────────────────

    def invalidate(self) -> None:
        """Drop cached scan results so the next access rebuilds from disk."""
        self._cached_index = None
        self._cached_all_entries = None

    @property
    def all_skills(self) -> list[SkillMetadata]:
        """All indexed skills after trust filtering (same as :meth:`build_index`)."""
        if self._cached_index is None:
            self.build_index()
        assert self._cached_index is not None
        return self._cached_index

    # ── Index build ───────────────────────────────────────────

    def build_index(self) -> list[SkillMetadata]:
        """Scan configured directories and return trusted skill metadata.

        Skips files that fail to parse. Omits ``blocked`` and ``quarantine`` trust levels.

        Returns:
            Sorted list: personal skills, then common, then procedures.
        """
        entries: list[SkillMetadata] = []
        seen_paths: set[Path] = set()

        def _add_metadata(meta: SkillMetadata) -> None:
            p = meta.path
            if p is None:
                return
            resolved = p.resolve()
            if resolved in seen_paths:
                return
            seen_paths.add(resolved)
            entries.append(meta)

        if self._skills_dir.exists():
            for skill_path in sorted(self._skills_dir.glob("*/SKILL.md")):
                try:
                    meta = load_skill_metadata(skill_path)
                    meta = meta.model_copy(update={"is_common": False, "is_procedure": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )

        if self._common_skills_dir.exists():
            for skill_path in sorted(self._common_skills_dir.glob("*/SKILL.md")):
                try:
                    meta = load_skill_metadata(skill_path)
                    meta = meta.model_copy(update={"is_common": True, "is_procedure": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )
            for skill_path in sorted(self._common_skills_dir.glob("*/*/SKILL.md")):
                try:
                    meta = load_skill_metadata(skill_path)
                    meta = meta.model_copy(update={"is_common": True, "is_procedure": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )

        if self._procedures_dir is not None and self._procedures_dir.exists():
            for proc_path in sorted(self._procedures_dir.glob("*.md")):
                try:
                    meta = load_skill_metadata(proc_path)
                    meta = meta.model_copy(update={"is_procedure": True, "is_common": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        proc_path,
                        exc,
                    )

        sorted_all = sorted(entries, key=self._sort_key)

        # Merge usage stats from SkillUsageTracker if anima_dir is available.
        #
        # Usage frequency policy: ``usage_count`` = view_count + use_count.
        # Currently only ``view`` events are emitted (on read_memory_file).
        # The ``use`` event type is reserved for future Skill-backed Cron
        # (Issue 7) where a cron job explicitly invokes a skill.  Until then,
        # ``view_count + success_count + failure_count`` serves as the
        # effective "how often is this skill actively used?" metric for
        # promotion decisions (Issue 4).
        if self._anima_dir is not None:
            try:
                from core.skills.usage import SkillUsageTracker

                tracker = SkillUsageTracker(self._anima_dir)
                all_stats = tracker.get_all_stats()
                for i, meta in enumerate(sorted_all):
                    stats = all_stats.get(meta.name)
                    if stats:
                        sorted_all[i] = meta.model_copy(
                            update={
                                "usage_count": stats.view_count + stats.use_count,
                                "success_count": stats.success_count,
                                "failure_count": stats.failure_count,
                                "patch_count": stats.patch_count,
                                "last_used_at": (
                                    datetime.fromisoformat(stats.last_used_at) if stats.last_used_at else None
                                ),
                            }
                        )
            except Exception:
                logger.debug("Failed to merge usage stats into index", exc_info=True)

        self._cached_all_entries = sorted_all
        filtered = [m for m in sorted_all if m.trust_level not in _EXCLUDED_TRUST_LEVELS]
        self._cached_index = filtered
        return list(filtered)

    @staticmethod
    def _sort_key(meta: SkillMetadata) -> tuple[int, str, str]:
        """Personal (0), common (1), procedures (2); then name and path."""
        if meta.is_procedure:
            tier = 2
        elif meta.is_common:
            tier = 1
        else:
            tier = 0
        path_s = str(meta.path) if meta.path is not None else ""
        return (tier, meta.name.casefold(), path_s)

    # ── Search ────────────────────────────────────────────────

    def search(self, query: str, *, include_blocked: bool = False) -> list[SkillMetadata]:
        """Return metadata entries matching *query* as a case-insensitive substring.

        Matches against ``name``, ``description``, and ``category`` (when set).

        Args:
            query: Substring to match.
            include_blocked: When ``False``, exclude ``blocked`` / ``quarantine`` entries.

        Returns:
            Filtered list in personal → common → procedure order.
        """
        if self._cached_all_entries is None:
            self.build_index()
        assert self._cached_all_entries is not None
        base = self._cached_all_entries if include_blocked else self.all_skills
        if not query:
            return list(base)
        q = query.casefold()

        def _matches(meta: SkillMetadata) -> bool:
            cat = meta.category
            return (
                q in meta.name.casefold()
                or q in meta.description.casefold()
                or (cat is not None and q in cat.casefold())
            )

        return [m for m in base if _matches(m)]
