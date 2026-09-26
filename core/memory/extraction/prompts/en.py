# Copyright 2026 AnimaWorks
# Licensed under the Apache License, Version 2.0
"""English prompts for entity / fact extraction."""

from __future__ import annotations

# ── Entity extraction ──────────────────────────────────────

ENTITY_SYSTEM = (
    "You are an information extraction agent. "
    "Extract entities (Person, Place, Organization, Concept, Event, Object, Time) "
    "from the given text in JSON format."
)

ENTITY_USER = """## Text
{content}

## Known Entities (reference)
{previous_entities}

## Instructions
Extract entities from the text above and return them in the following JSON format. Return an empty list if no entities are found.

```json
{{
  "entities": [
    {{"name": "canonical name", "entity_type": "Person|Place|Organization|Concept|Event|Object|Time", "summary": "1-2 sentence description"}}
  ]
}}
```"""

# ── Fact extraction ────────────────────────────────────────

FACT_SYSTEM = "You are a relationship extraction agent. Extract relationships between entity pairs in JSON format."

FACT_USER = """## Text
{content}

## Extracted Entities
{entities_json}

## Edge Types (edge_type)
Choose the most appropriate type from the list below. Use "RELATES_TO" if none fits.
{edge_types_list}

## Reference time (reference_time)
{reference_time}

## Instructions
For each fact, estimate when that fact became valid in the real world (valid_at):
- If the text states an explicit date or time, use it
- Resolve relative phrases like "yesterday" or "last week" using reference_time as the anchor
- If unclear, use reference_time unchanged (output as ISO 8601)

Extract relationships (facts) between the entities above and return them in the following JSON format. Return an empty list if no relationships are found.

```json
{{
  "facts": [
    {{"source_entity": "EntityA", "target_entity": "EntityB", "fact": "natural language description of relationship", "edge_type": "WORKS_AT", "valid_at": "YYYY-MM-DDTHH:MM:SS or null"}}
  ]
}}
```"""

# ── Community summarization ───────────────────────────────

COMMUNITY_SYSTEM = "You are a group analysis agent. Assign a name and summary to a group of related entities."

COMMUNITY_USER = """## Group Members
{members}

## Instructions
Based on the common theme of the members above, assign a name and summary to this group.

```json
{{"name": "group name (short)", "summary": "1-2 sentence description of this group"}}
```"""
