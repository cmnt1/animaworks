# Copyright 2026 AnimaWorks
# Licensed under the Apache License, Version 2.0
"""Pydantic models for entity / fact extraction results."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────

ENTITY_TYPES = Literal["Person", "Place", "Organization", "Concept", "Event", "Object", "Time"]

EDGE_TYPES = Literal[
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
]

EDGE_TYPE_DESCRIPTIONS: dict[str, str] = {
    "WORKS_AT": "Employment / affiliation",
    "LIVES_IN": "Residence / location",
    "KNOWS": "Personal acquaintance",
    "PREFERS": "Preference / taste",
    "SKILLED_IN": "Skill / ability",
    "PARTICIPATED_IN": "Participation / involvement",
    "CREATED": "Creation / authorship",
    "REPORTED": "Report / notification",
    "DEPENDS_ON": "Dependency",
    "RELATES_TO": "General (fallback)",
}

DEFAULT_EDGE_TYPE: str = "RELATES_TO"
_EDGE_TYPE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def normalize_edge_type_name(name: str) -> str:
    """Normalize a semantic edge type name to canonical upper snake case."""
    return str(name).strip().upper()


def is_valid_edge_type_name(name: str) -> bool:
    """Return True when *name* is a valid semantic edge type identifier."""
    return bool(_EDGE_TYPE_NAME_RE.fullmatch(normalize_edge_type_name(name)))


def default_edge_type_descriptions() -> dict[str, str]:
    """Return a mutable copy of the built-in semantic edge ontology."""
    return dict(EDGE_TYPE_DESCRIPTIONS)


def _coerce_edge_type_entry(entry: object) -> tuple[str, str] | None:
    name_obj: object | None
    description_obj: object | None

    if isinstance(entry, str):
        name_obj = entry
        description_obj = entry
    elif isinstance(entry, Mapping):
        if "name" in entry:
            name_obj = entry.get("name")
            description_obj = entry.get("description")
        elif len(entry) == 1:
            name_obj, description_obj = next(iter(entry.items()))
        else:
            return None
    else:
        name_obj = getattr(entry, "name", None)
        description_obj = getattr(entry, "description", None)

    if name_obj is None or description_obj is None:
        return None

    name = normalize_edge_type_name(str(name_obj))
    description = str(description_obj).strip()
    if not _EDGE_TYPE_NAME_RE.fullmatch(name) or not description:
        return None
    return name, description


def _edge_type_descriptions_from_entries(entries: object) -> dict[str, str]:
    if entries is None:
        return {}
    if isinstance(entries, Mapping) and "name" in entries:
        candidates: Iterable[object] = [entries]
    elif isinstance(entries, Mapping):
        candidates: Iterable[object] = ({"name": k, "description": v} for k, v in entries.items())
    elif isinstance(entries, str):
        candidates = [entries]
    else:
        try:
            candidates = entries  # type: ignore[assignment]
            iter(candidates)
        except TypeError:
            candidates = [entries]

    result: dict[str, str] = {}
    for entry in candidates:
        coerced = _coerce_edge_type_entry(entry)
        if coerced is None:
            logger.debug("Ignoring invalid Neo4j edge type config entry: %r", entry)
            continue
        name, description = coerced
        result[name] = description
    return result


def merge_edge_type_descriptions(*entry_sets: object) -> dict[str, str]:
    """Merge built-in and configured edge type descriptions.

    Later collections override earlier ones. Inputs may be mappings,
    ``{"name": ..., "description": ...}`` dicts, Pydantic config objects, or
    lists containing those shapes.
    """
    merged: dict[str, str] = {}
    for entries in entry_sets:
        merged.update(_edge_type_descriptions_from_entries(entries))
    return merged


def _load_configured_edge_type_entries() -> object:
    try:
        from core.config.models import load_config

        cfg = load_config()
        memory_cfg = getattr(cfg, "memory", None)
        return getattr(memory_cfg, "neo4j_edge_types", [])
    except Exception:
        logger.debug("Failed to load global Neo4j edge ontology config", exc_info=True)
        return []


def _load_status_edge_type_entries(anima_dir: Path | None) -> object:
    if anima_dir is None:
        return []
    status_path = Path(anima_dir) / "status.json"
    if not status_path.is_file():
        return []
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.debug("Failed to load per-anima Neo4j edge ontology config", exc_info=True)
        return []
    if not isinstance(data, Mapping):
        return []
    return data.get("neo4j_edge_types", [])


def resolve_edge_type_descriptions(anima_dir: Path | None = None) -> dict[str, str]:
    """Resolve semantic edge ontology from defaults, global config, and status.json."""
    return merge_edge_type_descriptions(
        EDGE_TYPE_DESCRIPTIONS,
        _load_configured_edge_type_entries(),
        _load_status_edge_type_entries(anima_dir),
    )


def allowed_edge_types(anima_dir: Path | None = None) -> frozenset[str]:
    """Return the canonical semantic edge types allowed for an Anima."""
    allowed = set(resolve_edge_type_descriptions(anima_dir))
    allowed.add(DEFAULT_EDGE_TYPE)
    return frozenset(allowed)


def format_edge_types_for_prompt(anima_dir: Path | None = None) -> str:
    """Format the resolved ontology for the fact extraction prompt."""
    descriptions = resolve_edge_type_descriptions(anima_dir)
    return "\n".join(f"- `{name}`: {description}" for name, description in descriptions.items())


def canonicalize_edge_type(
    edge_type: str | None,
    allowed: Collection[str] | None = None,
) -> tuple[str, str | None]:
    """Return ``(canonical_edge_type, raw_edge_type)`` for an extracted type."""
    allowed_names = {normalize_edge_type_name(name) for name in (allowed or EDGE_TYPE_DESCRIPTIONS)}
    allowed_names.add(DEFAULT_EDGE_TYPE)

    raw = "" if edge_type is None else str(edge_type).strip()
    if not raw:
        return DEFAULT_EDGE_TYPE, None

    canonical = normalize_edge_type_name(raw)
    if canonical in allowed_names:
        return canonical, None
    return DEFAULT_EDGE_TYPE, raw


# ── Entity models ──────────────────────────────────────────


class ExtractedEntity(BaseModel):
    """A single entity extracted from text."""

    name: str = Field(..., description="Canonical name")
    entity_type: ENTITY_TYPES = Field(default="Concept")
    summary: str = Field(default="", description="1-2 sentence summary")


class ExtractedFact(BaseModel):
    """A relationship between two entities."""

    source_entity: str = Field(..., description="Source entity name")
    target_entity: str = Field(..., description="Target entity name")
    fact: str = Field(..., description="Natural language relationship description")
    valid_at: str | None = Field(default=None, description="ISO datetime when fact became true")
    edge_type: str = Field(default="RELATES_TO", description="Relationship type from EDGE_TYPES")
    raw_edge_type: str | None = Field(
        default=None,
        description="Original LLM edge type when it was not part of the configured ontology",
    )


# ── Extraction results ────────────────────────────────────


class EntityExtractionResult(BaseModel):
    """LLM response for entity extraction."""

    entities: list[ExtractedEntity] = Field(default_factory=list)


class FactExtractionResult(BaseModel):
    """LLM response for fact extraction."""

    facts: list[ExtractedFact] = Field(default_factory=list)
