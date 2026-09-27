"""Regression tests for compact dynamic prompt sections."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.schemas import PromptConfig
from core.prompt.builder import (
    _build_resolution_registry_section,
    _dedupe_skill_catalog_metas,
    _limit_skill_catalog_entries,
    _skill_catalog_pointer,
)
from core.prompt.messaging import _build_messaging_section
from core.skills.models import SkillMetadata


def test_org_context_shortens_relationship_entries_without_model_or_path(data_dir, make_anima):
    make_anima("rin", supervisor="sakura", speciality="Example社 開発PdM（ProductX）")
    make_anima("sakura", speciality="Example社 COO")
    make_anima("aoi", supervisor="rin", speciality="Example社 エンジニア（監視・顧客対応）")

    from core.prompt.builder import _build_org_context

    result = _build_org_context("rin", ["sakura", "aoi"])

    assert "aoi (Example社 エンジニア)" in result
    assert "Sonnet" not in result
    assert str(data_dir / "animas" / "aoi") not in result
    assert "<animas_dir>/<名前>/" in result
    assert "部下操作の早見表" in result


def test_messaging_has_single_board_guidance_and_bounded_channel_list(tmp_path, monkeypatch):
    channels = (["team", "dept-a", "dept-b"], ["general", "ops", "public-a", "public-b", "public-c"])
    monkeypatch.setattr("core.prompt.messaging._collect_accessible_board_channels", lambda _: channels)
    monkeypatch.setattr("core.prompt.messaging._get_prompt_locale", lambda: "ja")

    result = _build_messaging_section(tmp_path / "rin", ["aoi"], execution_mode="a")

    assert "- - " not in result
    assert result.count("全体共有") == 1
    assert "所属チームの限定チャネル（報告先）" in result
    assert "#team" in result
    assert "ほか3件" in result
    assert "#public-c" not in result


def test_skill_catalog_deduplicates_by_description_and_obeys_ceiling():
    shared_prefix = "same description prefix shared across sources: " + "x" * 30
    procedure = SkillMetadata(
        name="procedure-copy",
        description=shared_prefix + " procedure",
        is_procedure=True,
    )
    skill = SkillMetadata(name="preferred-skill", description=shared_prefix + " skill")
    others = [SkillMetadata(name=f"other-{index}", description=f"unique description {index}") for index in range(4)]

    deduped = _dedupe_skill_catalog_metas([procedure, *others, skill])

    assert len(deduped) == 5
    assert any(_skill_catalog_pointer(meta) == "skills/preferred-skill/SKILL.md" for meta in deduped)
    assert all(meta.name != "procedure-copy" for meta in deduped)
    assert (
        len(_limit_skill_catalog_entries([meta.name for meta in deduped], PromptConfig().skill_catalog_max_items)) == 3
    )
    assert PromptConfig().skill_catalog_max_items == 3


def test_resolution_registry_excludes_unrelated_animas_and_omits_empty_section(tmp_path):
    memory = MagicMock()
    memory.read_resolutions.return_value = [
        {"ts": "2026-07-01T10:00:00", "resolver": "worker", "issue": "own issue"},
        {"ts": "2026-07-01T11:00:00", "resolver": "boss", "issue": "manager issue"},
        {"ts": "2026-07-01T12:00:00", "resolver": "peer", "issue": "unrelated issue"},
    ]
    memory.filter_resolutions_by_company.side_effect = lambda resolutions: resolutions

    with (
        patch("core.prompt.builder._related_resolution_resolvers", return_value={"worker", "boss", "child"}),
        patch(
            "core.prompt.builder.load_prompt",
            side_effect=lambda _name, **kwargs: f"## Resolved\n{kwargs['res_lines']}",
        ),
    ):
        section = _build_resolution_registry_section(tmp_path / "animas" / "worker", memory)

    assert "own issue" in section
    assert "manager issue" in section
    assert "unrelated issue" not in section

    memory.read_resolutions.return_value = [
        {"ts": "2026-07-01T12:00:00", "resolver": "peer", "issue": "unrelated issue"}
    ]
    with patch("core.prompt.builder._related_resolution_resolvers", return_value={"worker", "boss", "child"}):
        assert _build_resolution_registry_section(tmp_path / "animas" / "worker", memory) == ""


def test_current_state_templates_use_compact_review_heading():
    root = Path(__file__).resolve().parents[4] / "templates"
    ja = (root / "ja/prompts/builder/task_in_progress.md").read_text(encoding="utf-8")
    en = (root / "en/prompts/builder/task_in_progress.md").read_text(encoding="utf-8")

    assert "idle と判定する前に確認" in ja
    assert "check before determining idle" in en
    assert "MUST: 最優先" not in ja
    assert "MUST: Check first" not in en
