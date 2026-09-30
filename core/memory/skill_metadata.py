from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from core.schemas import SkillMeta


class SkillMetadataService:
    """Skill YAML frontmatter parsing and listing."""

    def __init__(self, skills_dir: Path, common_skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self._common_skills_dir = common_skills_dir

    @staticmethod
    def extract_skill_meta(path: Path, *, is_common: bool = False) -> SkillMeta:
        """Extract SkillMeta from a skill file's YAML frontmatter.

        Delegates to ``core.skills.loader.load_skill_metadata`` and converts
        via ``SkillMetadata.to_legacy()``.
        """
        from core.skills.loader import load_skill_metadata

        meta = load_skill_metadata(path)
        legacy = meta.to_legacy()
        legacy.is_common = is_common
        return legacy

    def list_skill_metas(self) -> list[SkillMeta]:
        """Return SkillMeta for each personal skill."""
        return [self.extract_skill_meta(f, is_common=False) for f in sorted(self._skills_dir.glob("*/SKILL.md"))]

    def list_common_skill_metas(self) -> list[SkillMeta]:
        """Return SkillMeta for each common skill (including nested subdirectories)."""
        if not self._common_skills_dir.is_dir():
            return []
        seen: set[Path] = set()
        results: list[SkillMeta] = []
        for pattern in ("*/SKILL.md", "*/*/SKILL.md"):
            for f in sorted(self._common_skills_dir.glob(pattern)):
                resolved = f.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                results.append(self.extract_skill_meta(f, is_common=True))
        return results
