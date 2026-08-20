"""Unit tests for external skill catalog pointers in core/prompt/builder.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from core.prompt.builder import _format_skill_catalog_line, _skill_catalog_pointer
from core.skills.models import SkillMetadata, SkillSource


def _external_meta(name: str, engine: str, path: Path) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description="External skill description",
        path=path,
        is_external=True,
        source=SkillSource(type="external", engine=engine),
    )


def test_external_pointer_returns_external_pointer() -> None:
    meta = _external_meta("foo", "claude", Path("/tmp/real/claude/foo/SKILL.md"))
    assert _skill_catalog_pointer(meta) == "external/claude/foo/SKILL.md"


def test_external_pointer_uses_engine_from_source() -> None:
    meta = _external_meta("bar", "codex", Path("/tmp/real/codex/bar/SKILL.md"))
    assert _skill_catalog_pointer(meta) == "external/codex/bar/SKILL.md"


def test_external_catalog_line_includes_ext_tag() -> None:
    meta = _external_meta("foo", "claude", Path("/tmp/real/claude/foo/SKILL.md"))
    line = _format_skill_catalog_line(
        meta,
        path=_skill_catalog_pointer(meta),
        common_label="common",
        procedure_label="procedure",
        desc_limit=250,
    )
    assert line.startswith("- external/claude/foo/SKILL.md")
    assert "[ext:claude]" in line


def test_non_external_common_pointer_unchanged() -> None:
    meta = SkillMetadata(
        name="foo",
        description="desc",
        path=Path("/tmp/shared/common_skills/foo/SKILL.md"),
        is_common=True,
    )
    assert _skill_catalog_pointer(meta) == "common_skills/foo/SKILL.md"


def test_non_external_personal_pointer_unchanged() -> None:
    meta = SkillMetadata(
        name="foo",
        description="desc",
        path=Path("/tmp/anima/skills/foo/SKILL.md"),
    )
    assert _skill_catalog_pointer(meta) == "skills/foo/SKILL.md"
