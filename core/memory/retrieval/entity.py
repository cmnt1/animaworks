from __future__ import annotations

# AnimaWorks - Digital Anima Framework
"""Deterministic entity/phrase extraction helpers for memory retrieval."""

import re
from functools import lru_cache

_QUOTE_RE = re.compile(r"[\"']([^\"']{3,80})[\"']")
_CAPITALIZED_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9+&'.-]*|[A-Z]{2,}[A-Za-z0-9+&'.-]*)"
    r"(?:\s+(?:of|the|and|for|to|by|in|on|at|with|"
    r"[A-Z][A-Za-z0-9+&'.-]*|[A-Z]{2,}[A-Za-z0-9+&'.-]*)){0,4}",
)
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]{2,}")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+'-]*|\d{4}|[\u3040-\u30ff\u3400-\u9fff]{2,}")

_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "all",
        "also",
        "an",
        "and",
        "answer",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "both",
        "by",
        "conversation",
        "did",
        "do",
        "does",
        "done",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "him",
        "his",
        "how",
        "in",
        "is",
        "it",
        "its",
        "kind",
        "like",
        "many",
        "mentioned",
        "of",
        "on",
        "or",
        "question",
        "recently",
        "session",
        "she",
        "some",
        "speaker",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "type",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whose",
        "why",
        "with",
    },
)


def extract_entities(
    text: str,
    *,
    ignored_entities: tuple[str, ...] = (),
    use_content_tokens: bool = True,
) -> set[str]:
    """Extract deterministic entity-like phrases without external NLP dependencies."""
    return set(_extract_entities_cached(text, ignored_entities, use_content_tokens))


@lru_cache(maxsize=4096)
def _extract_entities_cached(
    text: str,
    ignored_entities: tuple[str, ...],
    use_content_tokens: bool,
) -> frozenset[str]:
    ignored = {_normalize_entity(value) for value in ignored_entities}
    ignored.discard("")

    entities: set[str] = set()
    for match in _QUOTE_RE.finditer(text):
        _add_entity(entities, match.group(1), ignored)
    for match in _CAPITALIZED_RE.finditer(text):
        _add_entity(entities, match.group(0), ignored)
    for match in _CJK_RE.finditer(text):
        _add_entity(entities, match.group(0), ignored)

    if use_content_tokens:
        tokens = _content_tokens(text, ignored)
        entities.update(tokens)
        for size in (2, 3):
            for index in range(0, max(0, len(tokens) - size + 1)):
                phrase = " ".join(tokens[index : index + size])
                _add_entity(entities, phrase, ignored)
    return frozenset(entities)


def expand_alias_terms(
    text: str,
    alias_map: dict[str, tuple[str, ...]],
    *,
    limit: int = 8,
) -> tuple[str, ...]:
    """Return deterministic alias terms whose trigger phrases appear in text."""
    normalized = _normalize_entity(text)
    aliases: list[str] = []
    seen: set[str] = set()
    for trigger, values in alias_map.items():
        clean_trigger = _normalize_entity(trigger)
        if not clean_trigger or clean_trigger not in normalized:
            continue
        for value in values:
            alias = str(value or "").strip()
            key = alias.casefold()
            if not alias or key in seen:
                continue
            aliases.append(alias)
            seen.add(key)
            if len(aliases) >= limit:
                return tuple(aliases)
    return tuple(aliases)


def _add_entity(target: set[str], value: str, ignored: set[str]) -> None:
    entity = _normalize_entity(value)
    if _valid_entity(entity, ignored):
        target.add(entity)


def _normalize_entity(value: str) -> str:
    value = value.replace("’", "'")
    value = re.sub(r"[*_`#\[\](){}<>]", " ", value)
    value = re.sub(r"\b([A-Za-z]+)'s\b", r"\1", value)
    value = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u3400-\u9fff+&'-]+", " ", value)
    tokens = [token.strip("-'&+ ").lower() for token in value.split()]
    tokens = [token for token in tokens if token]
    while tokens and tokens[0] in _STOPWORDS:
        tokens.pop(0)
    while tokens and tokens[-1] in _STOPWORDS:
        tokens.pop()
    return " ".join(tokens)


def _valid_entity(entity: str, ignored: set[str]) -> bool:
    if not entity or entity in ignored or entity in _STOPWORDS:
        return False
    parts = entity.split()
    if any(part in ignored for part in parts):
        return False
    if len(parts) == 1:
        token = parts[0]
        return len(token) >= 3 and token not in _STOPWORDS
    return any(part not in _STOPWORDS and len(part) >= 3 for part in parts)


def _content_tokens(text: str, ignored: set[str]) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        token = _normalize_entity(match.group(0))
        if _valid_entity(token, ignored):
            tokens.append(token)
    return tokens[:120]
