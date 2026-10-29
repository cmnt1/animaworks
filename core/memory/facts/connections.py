from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Build entity connection graphs from active fact records."""

import json
import logging
import os
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

from core.memory.facts.entity_index import entity_registry_path, normalize_entity_key
from core.memory.facts.store import FactRecord, fact_entity_names, facts_dir, is_fact_active
from core.memory.frontmatter import parse_frontmatter
from core.time_utils import ensure_aware, now_local

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.RLock()
_FACT_CACHE: dict[str, tuple[tuple[Any, ...], tuple[_FactRow, ...], dict[str, str]]] = {}
# Finished answers keyed by the fact rows they were built from (rows are replaced when the files change).
_RESULT_CACHE: dict[tuple[Any, ...], tuple[tuple[_FactRow, ...], dict[str, Any]]] = {}
_RESULT_CACHE_MAX = 128


def _memo(key: tuple[Any, ...], rows: tuple[_FactRow, ...], build: Any) -> dict[str, Any]:
    with _CACHE_LOCK:
        hit = _RESULT_CACHE.get(key)
        if hit is not None and hit[0] is rows:
            return hit[1]
    result = build()
    with _CACHE_LOCK:
        if len(_RESULT_CACHE) >= _RESULT_CACHE_MAX:
            _RESULT_CACHE.pop(next(iter(_RESULT_CACHE)))
        _RESULT_CACHE[key] = (rows, result)
    return result


_FILE_EXTENSIONS = frozenset({".md", ".json", ".py", ".jsonl", ".yaml", ".yml", ".txt"})
_PARENTHESIS = ("（", "(")
_PERSON_SUFFIXES = ("さん", "様", "氏", "先生", "くん", "ちゃん")
_PLACE_CONTAINS = ("株式会社", "(株)", "（株）", "銀行", "病院", "クリニック", "不動産")
_PLACE_SUFFIXES = (
    "駅",
    "店",
    "会",
    "協会",
    "大学",
    "空港",
    "市",
    "県",
    "区",
    "ホテル",
    "FG",
)
_SERVICE_NAMES = frozenset(
    name.casefold()
    for name in (
        "Chatwork",
        "Slack",
        "Gmail",
        "Google",
        "Notion",
        "GitHub",
        "LINE",
        "Zoom",
        "Telegram",
        "Discord",
        "Beeper",
        "Obsidian",
        "AWS",
        "Hacker News",
        "X",
        "Twitter",
        "CodeRabbit",
    )
)
_FACT_FILENAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_FILE_BASENAMES = frozenset({"current_state", "current_task", "identity", "index", "log"})


@dataclass(frozen=True)
class _FactRow:
    record: FactRecord
    entities: tuple[str, ...]
    occurred_at: datetime | None
    recorded_at: str


def classify_entity(name: str, anima_names: set[str], user_names: set[str]) -> str:
    """Classify a canonical entity name without reading external state."""
    folded = name.strip().casefold()
    if _contains_name(anima_names, name):
        return "anima"
    if _contains_name(user_names, name):
        return "user"
    if any(folded.endswith(suffix) for suffix in _PERSON_SUFFIXES):
        return "person"
    if any(token.casefold() in folded for token in _PLACE_CONTAINS) or any(
        folded.endswith(suffix.casefold()) for suffix in _PLACE_SUFFIXES
    ):
        return "place"
    if folded in _SERVICE_NAMES or folded.endswith(".service"):
        return "service"
    return "topic"


def build_connections(
    anima_dir: Path,
    *,
    anima_names: set[str],
    user_names: set[str],
    days: int | None,
    limit: int = 40,
) -> dict[str, Any]:
    """Return the most common entities and their fact co-occurrences."""
    rows, aliases = _cached_fact_rows(Path(anima_dir))
    key = (
        "connections",
        str(anima_dir),
        days,
        limit,
        now_local().date().isoformat(),
        frozenset(anima_names),
        frozenset(user_names),
    )
    return _memo(
        key,
        rows,
        lambda: _build_connections(Path(anima_dir), rows, aliases, anima_names, user_names, days, limit),
    )


def _build_connections(
    anima_dir: Path,
    rows: tuple[_FactRow, ...],
    aliases: dict[str, str],
    anima_names: set[str],
    user_names: set[str],
    days: int | None,
    limit: int,
) -> dict[str, Any]:
    facts = _selected_rows(rows, days=days)
    names = _name_lookup(anima_names | user_names)
    self_name = Path(anima_dir).name

    node_counts: Counter[str] = Counter()
    last_seen: dict[str, str] = {}
    displays: dict[str, str] = {}
    fact_entities: list[tuple[str, ...]] = []
    for row in facts:
        canonical_entities = {
            key: display
            for raw_name in row.entities
            if (display := _canonical_entity(raw_name, aliases, names, user_names))
            and not _same_name(display, self_name)
            and not _looks_like_filename(display)
            and (key := _entity_key(display))
        }
        entities = tuple(sorted(canonical_entities))
        fact_entities.append(entities)
        for key, display in canonical_entities.items():
            displays.setdefault(key, display)
            node_counts[key] += 1
            if row.occurred_at is not None:
                seen_date = row.occurred_at.date().isoformat()
                if seen_date > last_seen.get(key, ""):
                    last_seen[key] = seen_date

    ranked_nodes = sorted(node_counts, key=lambda key: (-node_counts[key], displays[key].casefold(), key))[:limit]
    visible = set(ranked_nodes)
    link_counts: Counter[tuple[str, str]] = Counter()
    for entities in fact_entities:
        visible_entities = [entity for entity in entities if entity in visible]
        link_counts.update(combinations(visible_entities, 2))

    nodes = [
        {
            "id": displays[key],
            "label": displays[key],
            "kind": classify_entity(displays[key], anima_names, user_names),
            "count": node_counts[key],
            "last_seen": last_seen.get(key),
        }
        for key in ranked_nodes
    ]
    links = [
        {"source": displays[source], "target": displays[target], "weight": weight}
        for (source, target), weight in sorted(
            link_counts.items(),
            key=lambda item: (-item[1], displays[item[0][0]].casefold(), displays[item[0][1]].casefold()),
        )[: limit * 3]
    ]
    return {
        "anima": Path(anima_dir).name,
        "nodes": nodes,
        "links": links,
        "totals": {"facts": len(facts), "entities": len(node_counts)},
        "days": days,
    }


def entity_detail(
    anima_dir: Path,
    entity: str,
    *,
    anima_names: set[str],
    user_names: set[str],
    limit_facts: int = 20,
) -> dict[str, Any]:
    """Return facts, co-occurring entities, and memory files for one entity."""
    anima_dir = Path(anima_dir)
    rows, aliases = _cached_fact_rows(anima_dir)
    # Memory files are scanned too; reuse an answer for a minute at most.
    key = (
        "entity",
        str(anima_dir),
        entity,
        limit_facts,
        int(time.time() // 60),
        frozenset(anima_names),
        frozenset(user_names),
    )
    return _memo(
        key,
        rows,
        lambda: _entity_detail(anima_dir, rows, aliases, entity, anima_names, user_names, limit_facts),
    )


def _entity_detail(
    anima_dir: Path,
    rows: tuple[_FactRow, ...],
    aliases: dict[str, str],
    entity: str,
    anima_names: set[str],
    user_names: set[str],
    limit_facts: int,
) -> dict[str, Any]:
    names = _name_lookup(anima_names | user_names)
    query_name = _canonical_entity(entity, aliases, names, user_names)
    query_key = _entity_key(query_name) if query_name else ""
    self_name = anima_dir.name

    matches: list[_FactRow] = []
    related_counts: Counter[str] = Counter()
    displays: dict[str, str] = {}
    for row in _selected_rows(rows, days=None):
        canonical_entities = {
            key: display
            for raw_name in row.entities
            if (display := _canonical_entity(raw_name, aliases, names, user_names))
            and not _same_name(display, self_name)
            and not _looks_like_filename(display)
            and (key := _entity_key(display))
        }
        if query_key not in canonical_entities:
            continue
        matches.append(row)
        for key, display in canonical_entities.items():
            if key == query_key:
                continue
            displays.setdefault(key, display)
            related_counts[key] += 1

    matches.sort(key=lambda row: _sort_time(row.occurred_at), reverse=True)
    related = [
        {
            "id": displays[key],
            "kind": classify_entity(displays[key], anima_names, user_names),
            "weight": weight,
        }
        for key, weight in sorted(
            related_counts.items(),
            key=lambda item: (-item[1], displays[item[0]].casefold(), item[0]),
        )[:12]
    ]
    last_seen = max(
        (row.occurred_at.date().isoformat() for row in matches if row.occurred_at is not None),
        default=None,
    )
    files = _related_memory_files(anima_dir, query_name) if matches else []
    return {
        "entity": query_name or entity.strip(),
        "kind": classify_entity(query_name, anima_names, user_names) if query_name else "topic",
        "count": len(matches),
        "last_seen": last_seen,
        "facts": [
            {
                "fact_id": row.record.fact_id,
                "text": row.record.text,
                "recorded_at": row.recorded_at,
            }
            for row in matches[:limit_facts]
        ],
        "related": related,
        "files": files,
    }


def _cached_fact_rows(anima_dir: Path) -> tuple[tuple[_FactRow, ...], dict[str, str]]:
    facts_path = facts_dir(anima_dir)
    registry_path = entity_registry_path(anima_dir)
    fact_paths = sorted(facts_path.glob("*.jsonl")) if facts_path.is_dir() else []
    fact_signature_items: list[tuple[str, int, int]] = []
    for path in fact_paths:
        stat = _stat_or_none(path)
        if stat is not None:
            fact_signature_items.append((path.name, stat.st_size, stat.st_mtime_ns))
    fact_signature = tuple(fact_signature_items)
    registry_stat = _stat_or_none(registry_path)
    registry_mtime = registry_stat.st_mtime_ns if registry_stat is not None else None
    signature: tuple[Any, ...] = (fact_signature, registry_mtime)
    cache_key = str(anima_dir.resolve())

    with _CACHE_LOCK:
        cached = _FACT_CACHE.get(cache_key)
        if cached is not None and cached[0] == signature:
            return cached[1], cached[2]

        aliases = _read_registry_aliases(registry_path)
        rows: list[_FactRow] = []
        for path in fact_paths:
            try:
                with path.open(encoding="utf-8") as stream:
                    lines = stream.read().splitlines()
            except OSError:
                logger.warning("Failed to read facts file %s", path, exc_info=True)
                continue
            for line_no, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        continue
                    record = FactRecord.from_dict(raw)
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.warning("Skipping invalid fact line %s:%d", path, line_no)
                    continue
                if not is_fact_active(record):
                    continue
                occurred_at_text = str(raw.get("recorded_at") or raw.get("valid_at") or "").strip()
                occurred_at = _parse_timestamp(occurred_at_text)
                normalized_entities = tuple(
                    dict.fromkeys(_registry_canonical(name, aliases) for name in fact_entity_names(record))
                )
                rows.append(
                    _FactRow(
                        record=record,
                        entities=normalized_entities,
                        occurred_at=occurred_at,
                        recorded_at=occurred_at_text,
                    )
                )

        result = tuple(rows)
        _FACT_CACHE[cache_key] = (signature, result, aliases)
        return result, aliases


def _read_registry_aliases(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Failed to read entity registry %s", path, exc_info=True)
        return {}
    entities = payload.get("entities", {}) if isinstance(payload, dict) else {}
    if not isinstance(entities, dict):
        return {}
    aliases: dict[str, str] = {}
    for key, entry in sorted(entities.items(), key=lambda item: str(item[0])):
        if not isinstance(entry, dict):
            continue
        canonical = str(entry.get("canonical") or key).strip()
        if not canonical:
            continue
        raw_aliases = entry.get("aliases", [])
        aliases_list = raw_aliases if isinstance(raw_aliases, list) else []
        for name in (str(key), canonical, *(str(alias) for alias in aliases_list)):
            alias_key = normalize_entity_key(name)
            if alias_key:
                aliases.setdefault(alias_key, canonical)
    return aliases


def _registry_canonical(name: str, aliases: dict[str, str]) -> str:
    return aliases.get(normalize_entity_key(name), name.strip())


def _canonical_entity(
    name: str,
    aliases: dict[str, str],
    names: dict[str, str],
    user_names: set[str],
) -> str:
    clean = _registry_canonical(str(name), aliases).strip()
    if not clean:
        return ""
    if clean == "代表":
        return min(user_names, key=str.casefold) if user_names else clean

    base = _before_parenthesis(clean)
    if base and base.casefold() in names:
        return names[base.casefold()]
    known_name = names.get(clean.casefold())
    return known_name or clean


def _before_parenthesis(value: str) -> str:
    positions = [value.find(mark) for mark in _PARENTHESIS if mark in value]
    if not positions:
        return ""
    return value[: min(positions)].strip()


def _name_lookup(names: set[str]) -> dict[str, str]:
    return {name.casefold(): name for name in sorted(names, key=str.casefold) if name.strip()}


def _contains_name(names: set[str], name: str) -> bool:
    folded = name.strip().casefold()
    return any(candidate.strip().casefold() == folded for candidate in names)


def _entity_key(name: str) -> str:
    return normalize_entity_key(name) or name.strip().casefold()


def _same_name(left: str, right: str) -> bool:
    return _entity_key(left) == _entity_key(right)


def _looks_like_filename(name: str) -> bool:
    clean = name.strip()
    if not clean or "/" in clean or "\\" in clean:
        return True
    if Path(clean).suffix.casefold() in _FILE_EXTENSIONS:
        return True
    return bool(_FACT_FILENAME.fullmatch(clean)) and clean.casefold() in _FILE_BASENAMES


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _selected_rows(rows: tuple[_FactRow, ...], *, days: int | None) -> list[_FactRow]:
    active = [row for row in rows if is_fact_active(row.record)]
    if days is None:
        return active
    cutoff = now_local() - timedelta(days=days)
    return [row for row in active if row.occurred_at is not None and row.occurred_at >= cutoff]


def _sort_time(value: datetime | None) -> datetime:
    return value or datetime.min.replace(tzinfo=now_local().tzinfo)


def _stat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def _related_memory_files(anima_dir: Path, entity: str) -> list[dict[str, str]]:
    query = entity.casefold()
    matches: list[tuple[int, str, Path, str, str]] = []
    for memory_type in ("knowledge", "procedures"):
        root = anima_dir / memory_type
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            try:
                relative = path.relative_to(root)
                if "archive" in {part.casefold() for part in relative.parts}:
                    continue
                stat = path.stat()
                with path.open("rb") as stream:
                    content = stream.read(20 * 1024).decode("utf-8", errors="replace")
            except OSError:
                continue
            if query not in path.name.casefold() and query not in content.casefold():
                continue
            metadata, body = parse_frontmatter(content)
            title = str(metadata.get("title") or "").strip()
            if not title:
                title = next(
                    (line.lstrip("#").strip() for line in body.splitlines() if line.startswith("# ")),
                    path.stem,
                )
            matches.append((stat.st_mtime_ns, path.name.casefold(), path, memory_type, title))
    matches.sort(key=lambda item: (-item[0], item[1], str(item[2]).casefold()))
    return [
        {
            "memory_type": memory_type,
            "file": str(path.relative_to(anima_dir)),
            "title": title,
        }
        for _mtime, _name, path, memory_type, title in matches[:8]
    ]
