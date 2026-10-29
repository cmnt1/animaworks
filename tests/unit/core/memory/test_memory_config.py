from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for MemoryConfig schema."""

from core.config.schemas import AnimaWorksConfig, MemoryConfig


def test_memory_config_default() -> None:
    cfg = MemoryConfig()
    assert cfg.fact_edge_types == []


def test_memory_config_fact_edge_types() -> None:
    cfg = MemoryConfig(fact_edge_types=[{"name": "mentors", "description": "Mentorship"}])
    assert cfg.fact_edge_types[0].name == "MENTORS"


def test_memory_config_ignores_retired_backend_options() -> None:
    cfg = AnimaWorksConfig.model_validate(
        {
            "memory": {
                "backend": "neo4j",
                "neo4j": {"uri": "bolt://localhost:7687"},
                "neo4j_realtime_ingest": True,
                "neo4j_edge_types": [{"name": "MENTORS", "description": "old"}],
            }
        }
    )
    assert cfg.memory.fact_edge_types == []
    assert cfg.memory.model_dump() == {"fact_edge_types": []}


def test_animaworks_config_has_memory() -> None:
    cfg = AnimaWorksConfig()
    assert hasattr(cfg, "memory")
    assert isinstance(cfg.memory, MemoryConfig)
    assert cfg.memory.fact_edge_types == []
