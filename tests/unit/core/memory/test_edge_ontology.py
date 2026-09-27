# Copyright 2026 AnimaWorks
# Licensed under the Apache License, Version 2.0
"""Tests for Issue #21 — Edge Ontology Extension."""

from __future__ import annotations

import json
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory.facts.ontology import (
    DEFAULT_EDGE_TYPE,
    EDGE_TYPE_DESCRIPTIONS,
    EDGE_TYPES,
    ExtractedEntity,
    ExtractedFact,
    canonicalize_edge_type,
    format_edge_types_for_prompt,
    merge_edge_type_descriptions,
    resolve_edge_type_descriptions,
)

# ── Ontology definition tests ─────────────────────────────────────


class TestEdgeTypeDefinitions:
    """Verify EDGE_TYPES Literal and companion data."""

    def test_edge_types_contains_required_types(self) -> None:
        valid = frozenset(get_args(EDGE_TYPES))
        expected = {
            "WORKS_AT",
            "LIVES_IN",
            "KNOWS",
            "PREFERS",
            "SKILLED_IN",
            "PARTICIPATED_IN",
            "CREATED",
            "REPORTED",
            "DEPENDS_ON",
            "RELATES_TO",
        }
        assert expected == valid

    def test_default_edge_type_is_relates_to(self) -> None:
        assert DEFAULT_EDGE_TYPE == "RELATES_TO"

    def test_descriptions_cover_all_types(self) -> None:
        valid = frozenset(get_args(EDGE_TYPES))
        assert set(EDGE_TYPE_DESCRIPTIONS.keys()) == valid

    def test_descriptions_are_non_empty(self) -> None:
        for k, v in EDGE_TYPE_DESCRIPTIONS.items():
            assert v.strip(), f"Description for {k} is empty"

    def test_merge_custom_edge_types_with_defaults(self) -> None:
        merged = merge_edge_type_descriptions(
            EDGE_TYPE_DESCRIPTIONS,
            [{"name": "mentors", "description": "Mentorship relationship"}],
        )

        assert merged["WORKS_AT"] == "Employment / affiliation"
        assert merged["MENTORS"] == "Mentorship relationship"

    def test_memory_config_accepts_custom_fact_edge_types(self) -> None:
        from core.config.schemas import MemoryConfig

        cfg = MemoryConfig(
            fact_edge_types=[
                {"name": "mentors", "description": "Mentorship relationship"},
            ]
        )

        assert cfg.fact_edge_types[0].name == "MENTORS"
        assert cfg.fact_edge_types[0].description == "Mentorship relationship"

    def test_global_config_edge_types_are_resolved(self) -> None:
        from core.config.schemas import FactEdgeTypeConfig

        cfg = MagicMock()
        cfg.memory.fact_edge_types = [
            FactEdgeTypeConfig(name="mentors", description="Mentorship relationship"),
        ]

        with patch("core.config.models.load_config", return_value=cfg):
            descriptions = resolve_edge_type_descriptions()

        assert descriptions["MENTORS"] == "Mentorship relationship"

    def test_per_anima_status_edge_types_are_resolved(self, tmp_path) -> None:
        (tmp_path / "status.json").write_text(
            json.dumps(
                {
                    "fact_edge_types": [
                        {"name": "reports_to", "description": "Org reporting line"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        cfg = MagicMock()
        cfg.memory.fact_edge_types = []

        with patch("core.config.models.load_config", return_value=cfg):
            descriptions = resolve_edge_type_descriptions(tmp_path)

        assert descriptions["REPORTS_TO"] == "Org reporting line"

    def test_unknown_edge_type_canonicalization_preserves_raw(self) -> None:
        edge_type, raw_edge_type = canonicalize_edge_type("MENTORS", set(EDGE_TYPE_DESCRIPTIONS))

        assert edge_type == "RELATES_TO"
        assert raw_edge_type == "MENTORS"

    def test_configured_edge_type_canonicalization_preserves_semantics(self) -> None:
        edge_type, raw_edge_type = canonicalize_edge_type("mentors", {"MENTORS"})

        assert edge_type == "MENTORS"
        assert raw_edge_type is None


# ── ExtractedFact model tests ─────────────────────────────────────


class TestExtractedFactEdgeType:
    """Verify ExtractedFact edge_type field."""

    def test_default_edge_type(self) -> None:
        fact = ExtractedFact(
            source_entity="Alice",
            target_entity="Bob",
            fact="Alice knows Bob",
        )
        assert fact.edge_type == "RELATES_TO"

    def test_explicit_edge_type(self) -> None:
        fact = ExtractedFact(
            source_entity="Alice",
            target_entity="Acme",
            fact="Alice works at Acme",
            edge_type="WORKS_AT",
        )
        assert fact.edge_type == "WORKS_AT"

    def test_edge_type_in_serialization(self) -> None:
        fact = ExtractedFact(
            source_entity="Alice",
            target_entity="Tokyo",
            fact="Alice lives in Tokyo",
            edge_type="LIVES_IN",
        )
        data = fact.model_dump(mode="json")
        assert data["edge_type"] == "LIVES_IN"
        assert data["raw_edge_type"] is None

    def test_edge_type_from_json(self) -> None:
        raw = {
            "source_entity": "Alice",
            "target_entity": "Python",
            "fact": "Alice is skilled in Python",
            "edge_type": "SKILLED_IN",
        }
        fact = ExtractedFact.model_validate(raw)
        assert fact.edge_type == "SKILLED_IN"

    def test_missing_edge_type_defaults_to_relates_to(self) -> None:
        raw = {
            "source_entity": "A",
            "target_entity": "B",
            "fact": "A relates to B",
        }
        fact = ExtractedFact.model_validate(raw)
        assert fact.edge_type == "RELATES_TO"


# ── Extractor validation tests ────────────────────────────────────


class TestExtractorEdgeTypeValidation:
    """Verify edge_type validation in FactExtractor."""

    @pytest.mark.asyncio
    async def test_invalid_edge_type_falls_back_to_default(self) -> None:
        from core.memory.facts.extractor import FactExtractor

        extractor = FactExtractor(model="test-model")
        llm_response = json.dumps(
            {
                "facts": [
                    {
                        "source_entity": "Alice",
                        "target_entity": "Bob",
                        "fact": "Alice mentors Bob",
                        "edge_type": "MENTORS",
                    }
                ]
            }
        )

        cfg = MagicMock()
        cfg.memory.fact_edge_types = []
        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value=llm_response),
        ):
            entities = [
                MagicMock(name="Alice", spec=["name", "model_dump"]),
                MagicMock(name="Bob", spec=["name", "model_dump"]),
            ]
            entities[0].name = "Alice"
            entities[1].name = "Bob"
            entities[0].model_dump = lambda mode="json": {"name": "Alice", "entity_type": "Person", "summary": ""}
            entities[1].model_dump = lambda mode="json": {"name": "Bob", "entity_type": "Person", "summary": ""}

            facts = await extractor.extract_facts("Alice mentors Bob", entities)

        assert len(facts) == 1
        assert facts[0].edge_type == "RELATES_TO"
        assert facts[0].raw_edge_type == "MENTORS"

    @pytest.mark.asyncio
    async def test_valid_edge_type_preserved(self) -> None:
        from core.memory.facts.extractor import FactExtractor

        extractor = FactExtractor(model="test-model")
        llm_response = json.dumps(
            {
                "facts": [
                    {
                        "source_entity": "Alice",
                        "target_entity": "Acme",
                        "fact": "Alice works at Acme",
                        "edge_type": "WORKS_AT",
                    }
                ]
            }
        )

        cfg = MagicMock()
        cfg.memory.fact_edge_types = []
        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value=llm_response),
        ):
            entities = [
                MagicMock(name="Alice", spec=["name", "model_dump"]),
                MagicMock(name="Acme", spec=["name", "model_dump"]),
            ]
            entities[0].name = "Alice"
            entities[1].name = "Acme"
            entities[0].model_dump = lambda mode="json": {"name": "Alice", "entity_type": "Person", "summary": ""}
            entities[1].model_dump = lambda mode="json": {"name": "Acme", "entity_type": "Organization", "summary": ""}

            facts = await extractor.extract_facts("Alice works at Acme", entities)

        assert len(facts) == 1
        assert facts[0].edge_type == "WORKS_AT"
        assert facts[0].raw_edge_type is None

    @pytest.mark.asyncio
    async def test_configured_edge_type_from_status_is_preserved(self, tmp_path) -> None:
        from core.memory.facts.extractor import FactExtractor

        (tmp_path / "status.json").write_text(
            json.dumps({"fact_edge_types": [{"name": "mentors", "description": "Mentorship"}]}),
            encoding="utf-8",
        )
        cfg = MagicMock()
        cfg.memory.fact_edge_types = []
        extractor = FactExtractor(model="test-model", anima_dir=tmp_path)
        llm_response = json.dumps(
            {
                "facts": [
                    {
                        "source_entity": "Alice",
                        "target_entity": "Bob",
                        "fact": "Alice mentors Bob",
                        "edge_type": "mentors",
                    }
                ]
            }
        )

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value=llm_response),
        ):
            facts = await extractor.extract_facts(
                "Alice mentors Bob",
                [
                    ExtractedEntity(name="Alice", entity_type="Person"),
                    ExtractedEntity(name="Bob", entity_type="Person"),
                ],
            )

        assert len(facts) == 1
        assert facts[0].edge_type == "MENTORS"
        assert facts[0].raw_edge_type is None


# ── Prompt template tests ─────────────────────────────────────────


class TestPromptEdgeTypes:
    """Verify prompt templates include edge type instructions."""

    def test_ja_prompt_has_edge_types_placeholder(self) -> None:
        from core.memory.facts.prompts import ja

        assert "{edge_types_list}" in ja.FACT_USER
        assert "{reference_time}" in ja.FACT_USER
        assert "edge_type" in ja.FACT_USER

    def test_en_prompt_has_edge_types_placeholder(self) -> None:
        from core.memory.facts.prompts import en

        assert "{edge_types_list}" in en.FACT_USER
        assert "{reference_time}" in en.FACT_USER
        assert "edge_type" in en.FACT_USER

    def test_ja_prompt_formats_correctly(self) -> None:
        from core.memory.facts.prompts import ja

        edge_types_list = "\n".join(f"- `{k}`: {v}" for k, v in EDGE_TYPE_DESCRIPTIONS.items())
        result = ja.FACT_USER.format(
            content="test content",
            entities_json="[]",
            edge_types_list=edge_types_list,
            reference_time="2026-05-01T12:00:00+09:00",
        )
        assert "WORKS_AT" in result
        assert "RELATES_TO" in result

    def test_en_prompt_formats_correctly(self) -> None:
        from core.memory.facts.prompts import en

        edge_types_list = "\n".join(f"- `{k}`: {v}" for k, v in EDGE_TYPE_DESCRIPTIONS.items())
        result = en.FACT_USER.format(
            content="test content",
            entities_json="[]",
            edge_types_list=edge_types_list,
            reference_time="2026-05-01T12:00:00+09:00",
        )
        assert "WORKS_AT" in result
        assert "RELATES_TO" in result

    def test_prompt_edge_types_include_per_anima_status_config(self, tmp_path) -> None:
        (tmp_path / "status.json").write_text(
            json.dumps({"fact_edge_types": [{"name": "mentors", "description": "Mentorship"}]}),
            encoding="utf-8",
        )
        cfg = MagicMock()
        cfg.memory.fact_edge_types = []

        with patch("core.config.models.load_config", return_value=cfg):
            edge_types_list = format_edge_types_for_prompt(tmp_path)

        assert "`WORKS_AT`" in edge_types_list
        assert "`MENTORS`" in edge_types_list


# ── Import validation ─────────────────────────────────────────────


class TestOntologyImports:
    """Verify re-exports from __init__.py."""

    def test_import_edge_types_from_init(self) -> None:
        from core.memory.facts.ontology import EDGE_TYPES

        assert EDGE_TYPES is not None

    def test_import_edge_type_descriptions_from_init(self) -> None:
        from core.memory.facts.ontology import EDGE_TYPE_DESCRIPTIONS

        assert isinstance(EDGE_TYPE_DESCRIPTIONS, dict)

    def test_import_default_edge_type_from_init(self) -> None:
        from core.memory.facts.ontology import DEFAULT_EDGE_TYPE

        assert DEFAULT_EDGE_TYPE == "RELATES_TO"
