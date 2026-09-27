from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from core.config.schemas import FactEdgeTypeConfig, MemoryConfig, Neo4jEdgeTypeConfig
from core.memory.facts.ontology import resolve_edge_type_descriptions


def test_memory_fact_edge_types_are_loaded() -> None:
    memory_config = MemoryConfig(
        fact_edge_types=[FactEdgeTypeConfig(name="mentors", description="Mentorship relationship")]
    )
    with patch("core.config.models.load_config", return_value=SimpleNamespace(memory=memory_config)):
        descriptions = resolve_edge_type_descriptions()

    assert descriptions["MENTORS"] == "Mentorship relationship"


def test_legacy_neo4j_edge_types_are_loaded_when_new_key_is_absent() -> None:
    legacy_type = Neo4jEdgeTypeConfig(name="reports_to", description="Organizational reporting line")
    memory_config = MemoryConfig(neo4j_edge_types=[legacy_type])
    assert "fact_edge_types" not in memory_config.model_fields_set

    with patch("core.config.models.load_config", return_value=SimpleNamespace(memory=memory_config)):
        descriptions = resolve_edge_type_descriptions()

    assert descriptions["REPORTS_TO"] == "Organizational reporting line"


def test_status_fact_edge_types_override_global_config(tmp_path) -> None:
    global_type = FactEdgeTypeConfig(name="mentors", description="Global description")
    memory_config = MemoryConfig(fact_edge_types=[global_type])
    (tmp_path / "status.json").write_text(
        json.dumps(
            {
                "fact_edge_types": [{"name": "mentors", "description": "Per-anima description"}],
                "neo4j_edge_types": [{"name": "MENTORS", "description": "Legacy description"}],
            }
        ),
        encoding="utf-8",
    )

    with patch("core.config.models.load_config", return_value=SimpleNamespace(memory=memory_config)):
        descriptions = resolve_edge_type_descriptions(tmp_path)

    assert descriptions["MENTORS"] == "Per-anima description"
