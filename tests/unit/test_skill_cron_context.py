from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.config.models import SkillCronConfig
from core.skills.cron_context import build_cron_skill_context
from core.skills.index import SkillIndex
from core.skills.usage import SkillUsageTracker


def _write_skill(root: Path, name: str, *, body: str = "Use this skill.", extra: str = "") -> Path:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        "description: test skill\n"
        f"{extra}"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


def _write_common_skill(common_dir: Path, name: str, *, body: str = "Use this common skill.") -> Path:
    skill_dir = common_dir / "community" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        "description: common test skill\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


def _write_procedure(anima_dir: Path, name: str) -> Path:
    proc_dir = anima_dir / "procedures"
    proc_dir.mkdir(parents=True, exist_ok=True)
    path = proc_dir / f"{name}.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        "description: test procedure\n"
        "---\n\n"
        "Procedure body.\n",
        encoding="utf-8",
    )
    return path


def test_cron_context_rejects_unsafe_metadata_and_records_allowed_use(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    common_dir = tmp_path / "common_skills"
    common_dir.mkdir()

    _write_skill(anima_dir, "safe-skill", body="safe body")
    _write_skill(anima_dir, "warn-skill", extra="security:\n  verdict: warn\n")
    _write_skill(anima_dir, "caution-skill", extra="security:\n  verdict: caution\n")
    _write_skill(anima_dir, "dangerous-skill", extra="security:\n  verdict: dangerous\n")
    _write_skill(anima_dir, "blocked-skill", extra="trust_level: blocked\n")
    _write_skill(anima_dir, "destroy-skill", extra="risk:\n  destructive: true\n")
    _write_skill(anima_dir, "send-skill", extra="risk:\n  external_send: true\n")

    with patch("core.paths.get_common_skills_dir", return_value=common_dir):
        result = build_cron_skill_context(
            anima_dir,
            [
                "safe-skill",
                "warn-skill",
                "caution-skill",
                "dangerous-skill",
                "blocked-skill",
                "destroy-skill",
                "send-skill",
            ],
        )

    assert [item.name for item in result.attachments] == ["safe-skill"]
    assert "safe body" in result.render()
    assert {item.ref: item.reason for item in result.rejections} == {
        "warn-skill": "security_warn",
        "caution-skill": "security_caution",
        "dangerous-skill": "security_dangerous",
        "blocked-skill": "trust_level_blocked",
        "destroy-skill": "risk_destructive",
        "send-skill": "risk_external_send",
    }
    assert SkillUsageTracker(anima_dir).get_stats("safe-skill").use_count == 1
    assert SkillUsageTracker(anima_dir).get_stats("warn-skill").use_count == 0


def test_cron_context_resolves_name_priority_and_common_pointer(tmp_path: Path, caplog) -> None:
    anima_dir = tmp_path / "alice"
    common_dir = tmp_path / "common_skills"
    common_dir.mkdir()

    _write_skill(anima_dir, "shared", body="personal body")
    _write_common_skill(common_dir, "shared", body="common body")
    _write_procedure(anima_dir, "procedure-only")

    index = SkillIndex(anima_dir / "skills", common_dir, anima_dir / "procedures", anima_dir=anima_dir)
    with caplog.at_level(logging.WARNING):
        assert index.resolve_skill_reference("shared").path == anima_dir / "skills" / "shared" / "SKILL.md"
    assert "Multiple skill references matched 'shared'" in caplog.text
    assert index.resolve_skill_reference("procedure-only").is_procedure is True

    with patch("core.paths.get_common_skills_dir", return_value=common_dir):
        result = build_cron_skill_context(
            anima_dir,
            ["shared", "common_skills/community/shared/SKILL.md"],
        )

    assert [item.body.strip() for item in result.attachments] == ["personal body", "common body"]
    assert result.attachments[1].path == "common_skills/community/shared/SKILL.md"


def test_cron_context_truncates_large_bodies_without_rejecting(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    common_dir = tmp_path / "common_skills"
    common_dir.mkdir()

    _write_skill(anima_dir, "too-big", body="0123456789ABCDEF")
    _write_skill(anima_dir, "first", body="12345678")
    _write_skill(anima_dir, "second", body="abcdefgh")
    config = SimpleNamespace(
        skills=SimpleNamespace(
            cron=SkillCronConfig(
                max_skill_chars=10,
                max_total_chars=180,
            )
        )
    )

    with (
        patch("core.paths.get_common_skills_dir", return_value=common_dir),
        patch("core.skills.cron_context.load_config", return_value=config),
    ):
        result = build_cron_skill_context(anima_dir, ["too-big", "first", "second"])

    assert not result.rejections
    assert [(item.name, item.truncated, item.truncation_reason) for item in result.attachments] == [
        ("too-big", True, "max_skill_chars_exceeded"),
        ("first", False, None),
        ("second", True, "max_total_chars_exceeded"),
    ]
    rendered = result.render()
    assert "path: skills/too-big/SKILL.md" in rendered
    assert "0123456789ABCDEF" not in rendered
    assert SkillUsageTracker(anima_dir).get_stats("too-big").use_count == 1


def test_cron_context_allows_warn_with_warning_when_configured(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    common_dir = tmp_path / "common_skills"
    common_dir.mkdir()
    _write_skill(anima_dir, "warn-skill", body="warn body", extra="security:\n  verdict: warn\n")
    config = SimpleNamespace(skills=SimpleNamespace(cron=SkillCronConfig(allow_warn_caution=True)))

    with (
        patch("core.paths.get_common_skills_dir", return_value=common_dir),
        patch("core.skills.cron_context.load_config", return_value=config),
    ):
        result = build_cron_skill_context(anima_dir, ["warn-skill"])

    assert [item.name for item in result.attachments] == ["warn-skill"]
    assert [(item.ref, item.reason, item.name) for item in result.warnings] == [
        ("warn-skill", "security_warn_allowed", "warn-skill")
    ]
    assert SkillUsageTracker(anima_dir).get_stats("warn-skill").use_count == 1
