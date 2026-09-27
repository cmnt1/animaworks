"""Tests for the elastic skill catalog section contract."""

from __future__ import annotations

from core.prompt.assembler import PromptBudget, _allocate_sections
from core.prompt.builder import _skill_catalog_sections


def test_skill_catalog_is_a_single_elastic_section() -> None:
    entries = [f"- skills/ranked-{index}/SKILL.md: Short description {index}." for index in range(100)]
    sections = _skill_catalog_sections(entries)

    assert len(sections) == 1
    assert sections[0].id == "skill_catalog"
    assert sections[0].kind == "elastic"
    assert all(sections[0].content.count(entry + "\n") == 1 for entry in entries[:-1])
    assert entries[-1] in sections[0].content
    assert _allocate_sections(sections, PromptBudget(target=1, ceiling=1000)) == []


def test_skill_catalog_can_be_evicted_at_the_hard_ceiling() -> None:
    sections = _skill_catalog_sections(["- skills/test/SKILL.md: A test skill."])
    allocated = _allocate_sections(sections, PromptBudget(target=1, ceiling=10))
    assert allocated == []
