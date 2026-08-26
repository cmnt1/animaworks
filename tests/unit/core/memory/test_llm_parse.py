# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Tests for the shared memory LLM-output parse hardening (memory-llm-parse).

Covers the acceptance criteria for ``20260820_memory-llm-parse-hardening``:
  * `` ```json `` fences are stripped on every path
  * en template headings are accepted (procedure_from_resolved / session_summary)
  * broken-looking JSON is rescued by json_repair
  * parse failures log a warning (never silent drop)
  * local-model (no schema) path keeps working
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from core.memory._llm_parse import is_none_marker, load_json, strip_code_fence
from core.memory._llm_utils import supports_structured_output
from core.memory.distillation import ProceduralDistiller
from core.memory.extraction.extractor import FactExtractor
from core.memory.fact_observability import reset_warning_rate_limits


def _cfg(model: str = "test-model"):
    cfg = MagicMock()
    cfg.consolidation.llm_model = model
    cfg.credentials = {}
    cfg.anima_defaults.background_model = ""
    cfg.anima_defaults.background_credential = ""
    return cfg


def _run(coro):
    return asyncio.run(coro)


def _run_extractor(ext: FactExtractor, content: str) -> tuple[dict, list]:
    """Run an extractor entity call, capturing litellm kwargs and entities."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    captured: dict = {}

    def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return resp

    with (
        patch("litellm.acompletion", side_effect=_fake_acompletion),
        patch("core.memory._llm_utils.ensure_credentials_in_env"),
        patch("core.config.load_config", return_value=_cfg(ext._model)),
    ):
        entities = _run(ext.extract_entities("テスト"))

    return captured, entities


@pytest.fixture
def distiller(tmp_path) -> ProceduralDistiller:
    return ProceduralDistiller(anima_dir=tmp_path, anima_name="test-anima")


# ── Code-fence stripping ──────────────────────────────────────────────


class TestStripCodeFence:
    def test_json_fence(self) -> None:
        assert strip_code_fence('```json\n[]\n```') == "[]"

    def test_markdown_fence(self) -> None:
        text = "```markdown\n# Title\n\nBody.\n```"
        out = strip_code_fence(text)
        assert "```" not in out
        assert "# Title" in out

    def test_any_tag_fence(self) -> None:
        assert strip_code_fence("```ruby\nputs 1\n```") == "puts 1"

    def test_no_fence_returns_unchanged(self) -> None:
        assert strip_code_fence("plain text") == "plain text"

    def test_distiller_delegates(self, distiller) -> None:
        assert distiller._strip_code_fence('```json\n[1]\n```') == "[1]"

    def test_consolidation_sanitizer_json_fence(self) -> None:
        from core.memory.consolidation import ConsolidationEngine

        assert ConsolidationEngine._sanitize_llm_output('```json\n{"a": 1}\n```') == '{"a": 1}'


# ── Robust JSON loading (json_repair) ────────────────────────────────


class TestLoadJson:
    def test_plain(self) -> None:
        assert load_json('[{"title": "a", "content": "# A"}]') == [
            {"title": "a", "content": "# A"}
        ]

    def test_fenced(self) -> None:
        assert load_json('```json\n{"x": 1}\n```') == {"x": 1}

    def test_trailing_comma_rescued_by_json_repair(self) -> None:
        broken = '[{"title": "a", "content": "# A",}]'
        assert load_json(broken) == [{"title": "a", "content": "# A"}]

    def test_empty_returns_none(self) -> None:
        assert load_json("") is None
        assert load_json(None) is None

    def test_unparseable_warns_and_returns_none(self, caplog) -> None:
        from core.memory._llm_parse import logger as _parse_logger

        with (
            patch("json_repair.repair_json", return_value=None) as _rep,
            caplog.at_level("WARNING", logger=_parse_logger.name),
        ):
            assert load_json("garbage", context="test") is None
        assert _rep.called
        assert "Failed to parse test as JSON" in caplog.text


# ── en template support (procedure_from_resolved / classification) ────


class TestEnglishProcedureParsing:
    def test_parse_procedure_items_accepts_en_headings(self, distiller) -> None:
        text = (
            "## knowledge extraction\n(none)\n\n"
            "## procedure extraction\n"
            "- Filename: procedures/deploy.md\n"
            "  description: Deploy to production\n"
            "  tags: deploy, ops\n"
            "  Content: # Deploy\n\n1. Build\n2. Deploy"
        )
        items = distiller._parse_procedure_items(text)
        assert len(items) == 1
        assert items[0]["filename"] == "procedures/deploy.md"
        assert items[0]["description"] == "Deploy to production"
        assert items[0]["tags"] == ["deploy", "ops"]
        assert "Deploy" in items[0]["content"]

    def test_parse_knowledge_items_accepts_en_headings(self, distiller) -> None:
        text = (
            "## knowledge extraction\n"
            "- Filename: knowledge/api.md\n"
            "  Content: # API\n\nAlways be idempotent.\n\n"
            "## procedure extraction\n(none)"
        )
        items = distiller._parse_knowledge_items(text)
        assert len(items) == 1
        assert items[0]["filename"] == "knowledge/api.md"
        assert "idempotent" in items[0]["content"]

    def test_json_repair_in_weekly_pattern(self, distiller) -> None:
        broken = '```json\n[{"title": "t", "content": "# T",}]\n```'
        result = distiller._parse_procedures(broken)
        assert len(result) == 1
        assert result[0]["title"] == "t"


# ── en session summary parsing ───────────────────────────────────────


class TestEnglishSessionSummary:
    def test_en_state_change_extracts_resolved(self) -> None:
        from core.memory.conversation_finalize import _parse_session_summary

        raw = (
            "## Episode Summary\nTitle here\n\n"
            "**Counterparty**: Ace\n"
            "**Topics**: api, deploy\n\n"
            "## State Changes\n"
            "### Resolved\n"
            "- Fixed the API retry bug\n"
            "- Deployed the fix\n"
            "### New Tasks\n"
            "- Follow up with vendor by Friday\n"
            "### Current State\n"
            "Working on staging validation"
        )
        parsed = _parse_session_summary(raw)
        assert parsed.title == "Title here"
        assert "Fixed the API retry bug" in parsed.resolved_items
        assert "Deployed the fix" in parsed.resolved_items
        assert "vendor" in parsed.new_tasks[0]
        assert "staging" in parsed.current_status
        assert parsed.has_state_changes is True

    def test_is_none_marker(self) -> None:
        assert is_none_marker("(none)")
        assert is_none_marker("(なし)")
        assert is_none_marker(" (None) ")
        assert not is_none_marker("- actual item")


# ── Structured-output gating (API vs local) ─────────────────────────


class TestStructuredOutputGating:
    def test_api_families_enable_structured_output(self) -> None:
        assert supports_structured_output("anthropic/claude-sonnet-4-6") is True
        assert supports_structured_output("openai/gpt-4o") is True
        assert supports_structured_output("azure/gpt-4o") is True

    def test_local_models_stay_plain(self) -> None:
        assert supports_structured_output("ollama/qwen2.5") is False
        assert supports_structured_output("ollama/deepseek-r1") is False

    def test_extractor_adds_response_format_only_for_api(self) -> None:
        good_json = json.dumps(
            {"entities": [{"name": "A", "entity_type": "Person", "summary": "s"}]}
        )
        captured_api, _ = _run_extractor(FactExtractor(model="openai/gpt-4o", max_retries=1), good_json)
        assert captured_api.get("response_format") == {"type": "json_object"}

        captured_local, _ = _run_extractor(FactExtractor(model="ollama/qwen2.5", max_retries=1), good_json)
        assert "response_format" not in captured_local

    def test_extractor_repairs_broken_json(self) -> None:
        reset_warning_rate_limits()
        broken = '{"entities": [{"name": "A", "entity_type": "Person", "summary": "s",}]}'
        _, entities = _run_extractor(FactExtractor(model="test-model", max_retries=1), broken)
        assert len(entities) == 1
        assert entities[0].name == "A"
