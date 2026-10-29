# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for skill metadata extraction and matching."""

from __future__ import annotations

from pathlib import Path

from core.memory.skill_metadata import (
    SkillMetadataService,
)
from core.tooling.handler_base import _validate_skill_format

# ── Skill metadata extraction ────────────────────────────


class TestExtractSkillMeta:
    """Tests for SkillMetadataService.extract_skill_meta()."""

    def test_parse_yaml_frontmatter(self, tmp_path: Path) -> None:
        """YAML frontmatter with name + description is correctly parsed."""
        skill_file = tmp_path / "deploy.md"
        skill_file.write_text(
            "---\n"
            "name: deploy-skill\n"
            "description: デプロイ手順「deploy」「リリース」\n"
            "---\n"
            "\n"
            "# Deploy Skill\n"
            "\nBody content here.\n",
            encoding="utf-8",
        )

        meta = SkillMetadataService.extract_skill_meta(skill_file)

        assert meta.name == "deploy-skill"
        assert meta.description == "デプロイ手順「deploy」「リリース」"
        assert meta.path == skill_file
        assert meta.is_common is False

    def test_no_frontmatter_uses_filename(self, tmp_path: Path) -> None:
        """File without frontmatter uses filename stem as name, empty description."""
        skill_file = tmp_path / "my-skill.md"
        skill_file.write_text(
            "# My Skill\n\nSome instructions.\n",
            encoding="utf-8",
        )

        meta = SkillMetadataService.extract_skill_meta(skill_file)

        assert meta.name == "my-skill"
        assert meta.description == ""
        assert meta.path == skill_file

    def test_legacy_format_overview_section(self, tmp_path: Path) -> None:
        """Legacy format with ## 概要 extracts first line as description."""
        skill_file = tmp_path / "legacy.md"
        skill_file.write_text(
            "# レガシースキル\n\n## 概要\n\ncronジョブの設定と管理を行うスキル\n\n## 手順\n\n1. 手順内容\n",
            encoding="utf-8",
        )

        meta = SkillMetadataService.extract_skill_meta(skill_file)

        assert meta.name == "legacy"
        assert meta.description == "cronジョブの設定と管理を行うスキル"

    def test_frontmatter_with_extra_fields(self, tmp_path: Path) -> None:
        """Extra fields (version, metadata) do not interfere with extraction."""
        skill_file = tmp_path / "advanced.md"
        skill_file.write_text(
            "---\n"
            "name: advanced-tool\n"
            "description: 高度な検索「search」「query」\n"
            "version: 2.1\n"
            "metadata:\n"
            "  author: test\n"
            "  tags: [search, query]\n"
            "---\n"
            "\n"
            "Body.\n",
            encoding="utf-8",
        )

        meta = SkillMetadataService.extract_skill_meta(skill_file)

        assert meta.name == "advanced-tool"
        assert meta.description == "高度な検索「search」「query」"

    def test_is_common_flag(self, tmp_path: Path) -> None:
        """is_common flag is correctly set when specified."""
        skill_file = tmp_path / "shared.md"
        skill_file.write_text(
            "---\nname: shared-skill\ndescription: 共有スキル\n---\n\nContent.\n",
            encoding="utf-8",
        )

        meta_personal = SkillMetadataService.extract_skill_meta(skill_file, is_common=False)
        assert meta_personal.is_common is False

        meta_common = SkillMetadataService.extract_skill_meta(skill_file, is_common=True)
        assert meta_common.is_common is True


# ── Tier 1: Comma/delimiter keyword matching ────────────


# ── Tier 2: Description vocabulary matching ─────────────


# ── Personal-first ordering within tiers ─────────────────


# ── Deduplication across tiers ──────────────────────────


# ── Retriever parameter (Tier 3) ────────────────────────


# ── _validate_skill_format ──────────────────────────────


class TestValidateSkillFormat:
    """Tests for _validate_skill_format() in handler.py."""

    def test_valid_skill_returns_empty(self):
        content = "---\nname: my-skill\ndescription: テスト「keyword」\n---\n\n# My Skill\n"
        assert _validate_skill_format(content) == ""

    def test_missing_frontmatter(self):
        content = "# My Skill\n\nNo frontmatter."
        result = _validate_skill_format(content)
        assert "フロントマター" in result

    def test_missing_name_field(self):
        content = "---\ndescription: テスト「keyword」\n---\n\n# Skill\n"
        result = _validate_skill_format(content)
        assert "name" in result

    def test_missing_description_field(self):
        content = "---\nname: my-skill\n---\n\n# Skill\n"
        result = _validate_skill_format(content)
        assert "description" in result

    def test_no_bracket_keywords_warns(self):
        content = "---\nname: my-skill\ndescription: スキルの説明です\n---\n\n# Skill\n"
        result = _validate_skill_format(content)
        assert "キーワード" in result

    def test_legacy_section_warns(self):
        content = "---\nname: my-skill\ndescription: テスト「keyword」\n---\n\n## 概要\n\nLegacy content\n"
        result = _validate_skill_format(content)
        assert "旧形式" in result

    def test_valid_with_multiline_description(self):
        content = (
            "---\n"
            "name: my-skill\n"
            "description: >-\n"
            "  テストスキル。\n"
            "  「キーワード1」「キーワード2」\n"
            "---\n\n"
            "# My Skill\n"
        )
        assert _validate_skill_format(content) == ""


# ── Helper functions ────────────────────────────────────
