from __future__ import annotations

import json
from pathlib import Path

from core.anima.lifecycle import _format_hygiene_section
from core.i18n.strings.memory import STRINGS as MEMORY_STRINGS
from core.memory.maintenance.hygiene import scan_memory_hygiene


def _paths(report: dict, category: str) -> list[str]:
    return [entry["path"] for entry in report[category]]


def test_scan_detects_knowledge_categories_and_excludes_canonical_archive(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    knowledge = anima_dir / "knowledge"
    (knowledge / "nested").mkdir(parents=True)
    (knowledge / "archive").mkdir()
    (knowledge / "inherited-team").mkdir()
    for name in ("archived", "_archived", ".archive"):
        (knowledge / name).mkdir()

    (knowledge / "_merged_root.md").write_text("root", encoding="utf-8")
    (knowledge / "nested" / "_merged_nested.md").write_text("nested", encoding="utf-8")
    (knowledge / "notes.mdc").write_text("legacy", encoding="utf-8")
    (knowledge / "large.md").write_bytes(b"x" * (32 * 1024 + 1))
    (knowledge / "archive" / "_merged_ignored.md").write_text("ignored", encoding="utf-8")
    (knowledge / "archive" / "ignored.mdc").write_text("ignored", encoding="utf-8")
    episodes = anima_dir / "episodes"
    episodes.mkdir()
    (episodes / "legacy-recovery.md").write_text("not a hygiene candidate", encoding="utf-8")

    report = scan_memory_hygiene(anima_dir)

    assert set(report) == {
        "merged_leftovers",
        "inherited_dirs",
        "mdc_files",
        "oversized_knowledge",
        "noncanonical_archive_dirs",
    }
    assert _paths(report, "merged_leftovers") == [
        "knowledge/_merged_root.md",
        "knowledge/nested/_merged_nested.md",
    ]
    assert _paths(report, "inherited_dirs") == ["knowledge/inherited-team"]
    assert _paths(report, "mdc_files") == ["knowledge/notes.mdc"]
    assert _paths(report, "oversized_knowledge") == ["knowledge/large.md"]
    assert report["oversized_knowledge"][0]["size_bytes"] == 32 * 1024 + 1
    assert _paths(report, "noncanonical_archive_dirs") == [
        "knowledge/archived",
        "knowledge/_archived",
        "knowledge/.archive",
    ]
    assert all("first_seen" not in entry for entries in report.values() for entry in entries)
    assert json.loads((anima_dir / "state" / "memory_hygiene.json").read_text(encoding="utf-8")) == report


def test_scan_without_existing_report_or_knowledge_dir(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"

    report = scan_memory_hygiene(anima_dir)

    assert all(entries == [] for entries in report.values())
    assert (anima_dir / "state" / "memory_hygiene.json").is_file()


def test_hygiene_prompt_section_lists_items_caps_at_twenty_and_localizes() -> None:
    report = {
        "merged_leftovers": [{"path": f"knowledge/_merged_{index}.md"} for index in range(22)],
        "inherited_dirs": [],
        "mdc_files": [{"path": "knowledge/legacy.mdc"}],
        "oversized_knowledge": [{"path": "knowledge/large.md", "size_bytes": 40 * 1024}],
        "noncanonical_archive_dirs": [],
    }

    section = _format_hygiene_section(report, locale="en")

    assert "knowledge/_merged_0.md" in section
    assert "knowledge/_merged_19.md" in section
    assert "knowledge/_merged_20.md" not in section
    assert "2 more item(s)" in section
    assert "knowledge/legacy.mdc" in section
    assert "knowledge/large.md (40.0 KB)" in section
    assert _format_hygiene_section({key: [] for key in report}, locale="ja") == ""

    keys = (
        "memory_hygiene.header",
        "memory_hygiene.merged_leftovers",
        "memory_hygiene.inherited_dirs",
        "memory_hygiene.mdc_files",
        "memory_hygiene.oversized_knowledge",
        "memory_hygiene.noncanonical_archive_dirs",
        "memory_hygiene.remaining",
    )
    for locale in ("ja", "en", "ko"):
        for key in keys:
            assert key in MEMORY_STRINGS
            assert locale in MEMORY_STRINGS[key]
            assert MEMORY_STRINGS[key][locale]


def test_weekly_templates_include_hygiene_section_once() -> None:
    repository_root = Path(__file__).parents[4]
    for locale in ("ja", "en", "ko"):
        template = (
            repository_root / "templates" / locale / "prompts" / "memory" / "weekly_consolidation_instruction.md"
        ).read_text(encoding="utf-8")
        assert template.count("{hygiene_section}") == 1
        assert "{knowledge_files_list}" not in template
        assert template.count("{merge_candidates}") == 1
