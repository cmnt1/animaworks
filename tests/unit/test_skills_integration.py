from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for skill system: backward compat and catalog generation."""

from pathlib import Path

import pytest

from core.memory.skill_metadata import SkillMetadataService, match_skills_by_description
from core.schemas import SkillMeta
from core.skills.loader import load_skill_metadata
from core.skills.models import SkillTrustLevel
from core.tooling.skill_creator import create_skill_directory


def _write_skill(base: Path, name: str, *, desc: str = "", trust_level: str = "trusted") -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    content = (
        f"---\nname: {name}\ndescription: {desc or name + ' desc'}\n"
        f"trust_level: {trust_level}\n---\n\n# {name}\n"
    )
    (d / "SKILL.md").write_text(content, encoding="utf-8")
    return d


class TestSkillMetadataServiceBackwardCompat:
    """Verify SkillMetadataService still works after internal delegation."""

    def test_extract_skill_meta_returns_skill_meta(self, tmp_path: Path):
        d = tmp_path / "test-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: A test\nallowed_tools:\n  - github\n---\n\n# Test\n",
            encoding="utf-8",
        )
        meta = SkillMetadataService.extract_skill_meta(d / "SKILL.md", is_common=True)
        assert isinstance(meta, SkillMeta)
        assert meta.name == "test-skill"
        assert meta.description == "A test"
        assert meta.is_common is True
        assert meta.allowed_tools == ["github"]

    def test_list_skill_metas(self, tmp_path: Path):
        skills = tmp_path / "skills"
        common = tmp_path / "common"
        skills.mkdir()
        common.mkdir()
        _write_skill(skills, "alpha", desc="Alpha skill")
        _write_skill(skills, "beta", desc="Beta skill")

        svc = SkillMetadataService(skills, common)
        metas = svc.list_skill_metas()
        assert len(metas) == 2
        names = [m.name for m in metas]
        assert "alpha" in names
        assert "beta" in names
        assert all(not m.is_common for m in metas)

    def test_list_common_skill_metas(self, tmp_path: Path):
        skills = tmp_path / "skills"
        common = tmp_path / "common"
        skills.mkdir()
        common.mkdir()
        _write_skill(common, "shared-tool", desc="Shared tool")

        svc = SkillMetadataService(skills, common)
        metas = svc.list_common_skill_metas()
        assert len(metas) == 1
        assert metas[0].is_common is True

    def test_list_skill_summaries(self, tmp_path: Path):
        skills = tmp_path / "skills"
        common = tmp_path / "common"
        skills.mkdir()
        common.mkdir()
        _write_skill(skills, "my-skill", desc="My description")

        svc = SkillMetadataService(skills, common)
        summaries = svc.list_skill_summaries()
        assert summaries == [("my-skill", "My description")]


class TestMatchSkillsByDescription:
    """Verify existing match_skills_by_description still works with delegated extraction."""

    def test_tier1_match(self, tmp_path: Path):
        skills = tmp_path / "skills"
        skills.mkdir()
        _write_skill(skills, "chatwork-tool", desc="「チャットワーク」「chatwork」のメッセージ送受信ツール")

        svc = SkillMetadataService(skills, tmp_path / "common")
        metas = svc.list_skill_metas()
        matched = match_skills_by_description("チャットワークで送信して", metas)
        assert len(matched) >= 1
        assert matched[0].name == "chatwork-tool"


class TestSkillCreatorExtendedFrontmatter:
    """Verify create_skill_directory produces extended frontmatter."""

    def test_creates_with_trust_level_and_source(self, tmp_path: Path):
        result = create_skill_directory(
            skill_name="new-skill",
            description="A new skill",
            body="# New Skill\n\nBody content.",
            base_dir=tmp_path,
            allowed_tools=["web_search"],
            trust_level="community",
            source_type="anima",
            source_owner_anima="sakura",
            category="research",
        )
        assert "new-skill" in result

        skill_path = tmp_path / "new-skill" / "SKILL.md"
        assert skill_path.exists()

        meta = load_skill_metadata(skill_path)
        assert meta.name == "new-skill"
        assert meta.description == "A new skill"
        assert meta.trust_level == SkillTrustLevel.community
        assert meta.source.type == "anima"
        assert meta.source.owner_anima == "sakura"
        assert meta.category == "research"
        assert meta.allowed_tools == ["web_search"]
        assert meta.version == 1

    def test_defaults_to_trusted(self, tmp_path: Path):
        create_skill_directory(
            skill_name="default-skill",
            description="Default trust",
            body="# Default\n\nBody.",
            base_dir=tmp_path,
        )
        meta = load_skill_metadata(tmp_path / "default-skill" / "SKILL.md")
        assert meta.trust_level == SkillTrustLevel.trusted
        assert meta.source.origin == "manual"


class TestBuilderTrustTag:
    """Test the _format_trust_tag helper used in builder catalog."""

    def test_trusted_shows_no_tag(self):
        from core.prompt.builder import _format_trust_tag

        class FakeMeta:
            trust_level = SkillTrustLevel.trusted

        assert _format_trust_tag(FakeMeta()) == ""

    def test_official_shows_tag(self):
        from core.prompt.builder import _format_trust_tag

        class FakeMeta:
            trust_level = SkillTrustLevel.official

        assert _format_trust_tag(FakeMeta()) == " [official]"

    def test_builtin_shows_tag(self):
        from core.prompt.builder import _format_trust_tag

        class FakeMeta:
            trust_level = SkillTrustLevel.builtin

        assert _format_trust_tag(FakeMeta()) == " [builtin]"

    def test_no_trust_level_returns_empty(self):
        from core.prompt.builder import _format_trust_tag

        class FakeMeta:
            pass

        assert _format_trust_tag(FakeMeta()) == ""
