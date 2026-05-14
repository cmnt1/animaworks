# Copyright 2026 AnimaWorks
# Licensed under the Apache License, Version 2.0
from __future__ import annotations

from core.memory.ontology.default import (
    DEFAULT_EDGE_TYPE,
    EDGE_TYPE_DESCRIPTIONS,
    EDGE_TYPES,
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedFact,
    FactExtractionResult,
    allowed_edge_types,
    canonicalize_edge_type,
    default_edge_type_descriptions,
    format_edge_types_for_prompt,
    is_valid_edge_type_name,
    merge_edge_type_descriptions,
    normalize_edge_type_name,
    resolve_edge_type_descriptions,
)

__all__ = [
    "DEFAULT_EDGE_TYPE",
    "EDGE_TYPE_DESCRIPTIONS",
    "EDGE_TYPES",
    "ExtractedEntity",
    "ExtractedFact",
    "EntityExtractionResult",
    "FactExtractionResult",
    "allowed_edge_types",
    "canonicalize_edge_type",
    "default_edge_type_descriptions",
    "format_edge_types_for_prompt",
    "is_valid_edge_type_name",
    "merge_edge_type_descriptions",
    "normalize_edge_type_name",
    "resolve_edge_type_descriptions",
]
