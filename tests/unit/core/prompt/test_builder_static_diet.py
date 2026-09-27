from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.i18n import t
from core.memory.priming import PrimingResult, format_priming_section
from core.paths import load_prompt
from core.prompt.builder import (
    TIER_MICRO,
    _build_emotion_instruction,
    _build_group1,
    _build_group4,
    _build_human_notification_guidance,
    build_system_prompt,
)
from core.prompt.tool_content import load_guide
from core.schemas import VALID_EMOTIONS


def _prompt_config(*, threshold: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        prompt=SimpleNamespace(
            injection_size_warning_chars=threshold,
            identity_business_exclude_headings=[
                "外見",
                "基本プロフィール",
                "Appearance",
                "Basic Profile",
            ],
            skill_catalog_router_enabled=False,
            skill_catalog_router_top_k=5,
            skill_catalog_router_min_score=1.15,
            skill_catalog_router_include_body=True,
            skill_catalog_router_dense_enabled=True,
            skill_catalog_router_dense_weight=8.0,
            skill_catalog_max_items=3,
        )
    )


def _sections_by_id(sections):
    return {section.id: section.content for section in sections}


def _build_minimal_prompt(memory, data_dir: Path, trigger: str) -> str:
    with (
        patch("core.config.load_config", return_value=_prompt_config()),
        patch("core.prompt.builder._discover_other_animas", return_value=[]),
        patch("core.prompt.builder._build_group2", return_value=[]),
        patch("core.prompt.builder._build_group3", return_value=[]),
        patch("core.prompt.builder._build_group4", return_value=[]),
        patch("core.prompt.builder._build_group5", return_value=[]),
        patch("core.prompt.builder._build_group6", return_value=[]),
        patch("core.skills.SkillIndex", return_value=SimpleNamespace(all_skills=[])),
    ):
        return build_system_prompt(memory, trigger=trigger, context_window=8000).system_prompt


def test_business_trigger_identity_omits_profile_but_chat_keeps_full_text(data_dir: Path, tmp_path: Path) -> None:
    identity = "## 基本プロフィール\nProfile\n## 外見\nAppearance\n## 役割\nRole"
    memory = SimpleNamespace(read_identity=lambda: identity, read_injection=lambda: "")
    with patch("core.config.load_config", return_value=_prompt_config()):
        business = _sections_by_id(
            _build_group1(Path("/tmp/animas/alice"), Path("/tmp/data"), memory, False, {}, tier=TIER_MICRO)
        )
        chat = _sections_by_id(
            _build_group1(
                Path("/tmp/animas/alice"),
                Path("/tmp/data"),
                memory,
                False,
                {},
                tier=TIER_MICRO,
                is_chat=True,
            )
        )

    assert "## 外見" not in business["identity"]
    assert "## 基本プロフィール" not in business["identity"]
    assert "## 役割" in business["identity"]
    assert chat["identity"] == identity

    integrated_memory = SimpleNamespace(
        anima_dir=tmp_path / "animas" / "alice",
        read_identity=lambda: identity,
        read_injection=lambda: "",
        read_permissions=lambda: "",
    )
    integrated_memory.anima_dir.mkdir(parents=True)
    heartbeat_prompt = _build_minimal_prompt(integrated_memory, data_dir, "heartbeat")
    chat_prompt = _build_minimal_prompt(integrated_memory, data_dir, "chat")
    assert "## 外見" not in heartbeat_prompt
    assert "## 外見" in chat_prompt


def test_identity_without_h2_or_with_only_excluded_sections_falls_back_to_original() -> None:
    from core.prompt.builder import _filter_identity_business_sections

    assert _filter_identity_business_sections("No headings here", ["外見"]) == "No headings here"
    identity = "## 外見\nOnly excluded content"
    assert _filter_identity_business_sections(identity, ["外見"]) == identity


def test_skill_catalog_router_uses_prompt_schema_defaults_when_config_fails() -> None:
    from core.config.schemas import PromptConfig
    from core.prompt.builder import _load_skill_catalog_router_settings, _SkillCatalogRouterSettings

    with patch("core.config.load_config", side_effect=RuntimeError("config unavailable")):
        settings = _load_skill_catalog_router_settings()

    prompt = PromptConfig()
    expected = _SkillCatalogRouterSettings(
        enabled=prompt.skill_catalog_router_enabled,
        top_k=prompt.skill_catalog_router_top_k,
        min_score=prompt.skill_catalog_router_min_score,
        include_body=prompt.skill_catalog_router_include_body,
        dense_enabled=prompt.skill_catalog_router_dense_enabled,
        dense_weight=prompt.skill_catalog_router_dense_weight,
        max_items=prompt.skill_catalog_max_items,
    )
    assert settings == expected


def test_injection_size_warning_is_only_added_for_consolidation() -> None:
    memory = SimpleNamespace(read_identity=lambda: "", read_injection=lambda: "oversized injection")
    with patch("core.config.load_config", return_value=_prompt_config(threshold=5)):
        ordinary = _sections_by_id(
            _build_group1(Path("/tmp/animas/alice"), Path("/tmp/data"), memory, False, {}, tier=TIER_MICRO)
        )
        consolidation = _sections_by_id(
            _build_group1(
                Path("/tmp/animas/alice"),
                Path("/tmp/data"),
                memory,
                False,
                {},
                tier=TIER_MICRO,
                is_consolidation=True,
            )
        )

    assert "injection_size_warning" not in ordinary
    assert "injection_size_warning" in consolidation


def test_prompt_warning_uses_actual_trigger_classification(data_dir: Path, tmp_path: Path) -> None:
    memory = SimpleNamespace(
        anima_dir=tmp_path / "animas" / "alice",
        read_identity=lambda: "",
        read_injection=lambda: "oversized injection",
        read_permissions=lambda: "",
    )
    memory.anima_dir.mkdir(parents=True)
    with patch("core.config.load_config", return_value=_prompt_config(threshold=5)):
        heartbeat = _build_minimal_prompt(memory, data_dir, "heartbeat")
        chat = _build_minimal_prompt(memory, data_dir, "chat")
        consolidation = _build_minimal_prompt(memory, data_dir, "consolidation:daily")

    assert '<section name="injection_size_warning">' not in heartbeat
    assert '<section name="injection_size_warning">' not in chat
    assert '<section name="injection_size_warning">' in consolidation


def test_mode_s_tool_guides_are_compact_and_keep_safety_constraints(data_dir: Path, tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    anima_dir.mkdir(parents=True)
    skill_index = SimpleNamespace(all_skills=[])
    groups = _build_group4(
        anima_dir,
        data_dir,
        SimpleNamespace(anima_dir=anima_dir),
        1.0,
        "s",
        skill_index,
        False,
        False,
        False,
        False,
        None,
        None,
        {},
        {},
    )
    content = _sections_by_id(groups)
    guide = content["tool_guides"]

    assert len(guide) <= 700
    assert guide.count("20分") == 1
    assert "state/cmd_output/{id}.txt" in guide
    assert "ACTION-RULE" in guide
    assert "max" in guide or "最大2宛先" in guide
    assert "delegate_task" in guide
    assert "animaworks-tool --help" in guide


def test_memory_guide_is_under_500_and_hints_are_merged(data_dir: Path, tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    anima_dir.mkdir(parents=True)
    groups = _build_group4(
        anima_dir,
        data_dir,
        SimpleNamespace(anima_dir=anima_dir),
        1.0,
        "s",
        SimpleNamespace(all_skills=[]),
        False,
        False,
        False,
        False,
        None,
        None,
        {},
        {},
    )
    content = _sections_by_id(groups)

    assert len(content["memory_guide"]) <= 500
    assert "common_knowledge/operations/action-rules-guide.md" in content["memory_guide"]
    assert "reference/" in content["memory_guide"]
    assert "common_knowledge_hint" not in content
    assert "reference_hint" not in content


def test_emotion_and_human_notification_guidance_meet_size_limits() -> None:
    emotion = _build_emotion_instruction()
    notification = _build_human_notification_guidance("s")

    assert len(emotion) <= 250
    assert "<!-- emotion:" in emotion
    assert "neutral" in emotion
    assert len(notification) <= 250
    assert "call_human" in notification
    assert "検証できない" in notification or "unverified" in notification


def test_external_tool_categories_are_one_line_and_direct_hint_is_mode_specific(data_dir: Path) -> None:
    anima_dir = Path("/tmp/animas/alice")
    arguments = (
        anima_dir,
        data_dir,
        SimpleNamespace(anima_dir=anima_dir),
        1.0,
        "s",
        SimpleNamespace(all_skills=[]),
        False,
        False,
        False,
        False,
    )
    mode_s = _sections_by_id(_build_group4(*arguments, ["calendar", "slack"], None, {}, {}))
    mode_b = _sections_by_id(_build_group4(*arguments[:4], "b", *arguments[5:], ["calendar", "slack"], None, {}, {}))

    assert mode_s["external_tools"].splitlines()[0].endswith("calendar, slack")
    assert len(mode_s["external_tools"].splitlines()) == 2
    assert len(mode_b["external_tools"].splitlines()) == 1


def test_static_prompt_templates_meet_size_budgets_in_all_locales() -> None:
    emotion_list = ", ".join(sorted(VALID_EMOTIONS))
    for locale in ("ja", "en", "ko"):
        memory = load_prompt("memory_guide", locale=locale, anima_dir=Path("/tmp/animas/alice")).strip()
        emotion = load_prompt("builder/emotion_instruction", locale=locale, emotion_list=emotion_list).strip()
        notification = load_prompt("builder/human_notification", locale=locale).strip()
        tool_guides = "\n\n".join(
            part
            for part in (
                t("tool_guide.host_tools.s", locale=locale),
                load_guide("s_builtin", locale=locale).strip(),
                load_guide("s_mcp", locale=locale).strip(),
            )
            if part
        )

        assert len(memory) <= 500
        assert len(emotion) <= 250
        assert len(notification) <= 250
        assert len(tool_guides) <= 800


def test_empty_priming_has_no_headers_or_subheaders() -> None:
    assert format_priming_section(PrimingResult()) == ""
    assert format_priming_section(PrimingResult(related_knowledge=" \n\t")) == ""
    assert format_priming_section(PrimingResult(pending_human_notifications="notice")) == ""


def test_own_personal_tools_are_counted_not_listed(data_dir: Path, tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    (anima_dir / "tools").mkdir(parents=True)
    own = anima_dir / "tools" / "one_off_pdf.py"
    own.write_text("", encoding="utf-8")
    common = tmp_path / "common_tools" / "obsidian_note.py"
    common.parent.mkdir()
    common.write_text("", encoding="utf-8")
    arguments = (
        anima_dir,
        data_dir,
        SimpleNamespace(anima_dir=anima_dir),
        1.0,
        "s",
        SimpleNamespace(all_skills=[]),
        False,
        False,
        False,
        False,
    )
    personal = {"one_off_pdf": str(own), "obsidian_note": str(common)}
    content = _sections_by_id(_build_group4(*arguments, ["slack"], personal, {}, {}))["external_tools"]

    assert "one_off_pdf" not in content
    assert "obsidian_note, slack" in content
    assert t("builder.external_tools.personal_count", count=1) in content


def test_only_personal_tools_still_render_count(data_dir: Path, tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "bob"
    (anima_dir / "tools").mkdir(parents=True)
    own = anima_dir / "tools" / "mine.py"
    own.write_text("", encoding="utf-8")
    arguments = (
        anima_dir,
        data_dir,
        SimpleNamespace(anima_dir=anima_dir),
        1.0,
        "b",
        SimpleNamespace(all_skills=[]),
        False,
        False,
        False,
        False,
    )
    content = _sections_by_id(_build_group4(*arguments, [], {"mine": str(own)}, {}, {}))["external_tools"]

    assert content.strip() == t("builder.external_tools.personal_count", count=1)
