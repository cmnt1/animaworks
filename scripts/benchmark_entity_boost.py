from __future__ import annotations

"""Compare legacy registry scanning with the entity-boost automaton."""

import json
import tempfile
import time
from pathlib import Path

import core.memory.retrieval.entity as entity_module
from core.memory.entity_index import normalize_entity_key
from core.memory.retrieval.entity import EntityAliasIndex, EntityBoostConfig, apply_entity_boost


def _legacy_match(text: str, index: EntityAliasIndex | None) -> set[str]:
    if not index or not text:
        return set()
    cached = index.match_cache.get(text)
    if cached is not None:
        return set(cached)
    haystacks = {normalize_entity_key(text), entity_module._normalize_entity(text), text.casefold()}
    haystacks.discard("")
    matched = {
        key
        for key, surfaces in index.synonyms.items()
        if any(len(surface) >= 2 and surface in haystack for surface in surfaces for haystack in haystacks)
    }
    index.match_cache[text] = frozenset(matched)
    return matched


def _legacy_resolve(phrases: set[str], index: EntityAliasIndex) -> set[str]:
    keys: set[str] = set()
    for phrase in phrases:
        for form in (entity_module._normalize_entity(phrase), normalize_entity_key(phrase), phrase.casefold()):
            owner = index.alias_owner.get(form)
            if owner:
                keys.add(owner)
                break
        keys |= _legacy_match(phrase, index)
    return keys


def _run_legacy(config: EntityBoostConfig, candidates: list[dict[str, object]]) -> float:
    entity_module.clear_entity_alias_index_cache()
    started = time.perf_counter()
    index = entity_module.load_entity_alias_index(config.anima_dir)
    assert index is not None
    query = "alias003 repayment"
    query_entities = entity_module.extract_entities(query)
    _legacy_match(query, index)
    _legacy_resolve(query_entities, index)
    for candidate in candidates:
        content = str(candidate["content"])
        candidate_entities = entity_module.extract_entities(content)
        _legacy_match(content, index)
        _legacy_resolve(candidate_entities, index)
        for value in candidate_entities:
            _legacy_resolve({value}, index)
    return time.perf_counter() - started


def _run_automaton(config: EntityBoostConfig, candidates: list[dict[str, object]]) -> float:
    entity_module.clear_entity_alias_index_cache()
    started = time.perf_counter()
    apply_entity_boost("alias003 repayment", candidates, config)
    return time.perf_counter() - started


def main() -> None:
    entities = {
        f"entity{i:03d}": {
            "canonical": f"Entity {i:03d}",
            "aliases": [f"alias{i:03d}"],
            "source_fact_ids": [],
        }
        for i in range(400)
    }
    candidates = [
        {
            "content": (f"alias{i:03d} " + " ".join(f"token{i:03d}{j:03d}" for j in range(140)))[:1024],
            "score": i / 1000,
        }
        for i in range(100)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        anima_dir = Path(tmp)
        state_dir = anima_dir / "state"
        state_dir.mkdir()
        (state_dir / "entity_registry.json").write_text(
            json.dumps({"entities": entities}, ensure_ascii=False),
            encoding="utf-8",
        )
        config = EntityBoostConfig(enabled=True, anima_dir=anima_dir, prefer_candidate_metadata=False)
        legacy_seconds = _run_legacy(config, candidates)
        automaton_seconds = _run_automaton(config, candidates)

    print(f"legacy: {legacy_seconds:.3f}s")
    print(f"automaton: {automaton_seconds:.3f}s")
    print(f"speedup: {legacy_seconds / automaton_seconds:.1f}x")


if __name__ == "__main__":
    main()
