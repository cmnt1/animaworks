from __future__ import annotations

# AnimaWorks - Digital Anima Framework
"""Deterministic LoCoMo fact records for retrieval-only dual-index ablations."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

_SESSION_RE = re.compile(r"^session_(\d+)$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class LocomoFactRecord:
    """One ADD-only, source-grounded fact-like LoCoMo memory record."""

    fact_id: str
    text: str
    valid_at: str
    event_time_iso: str
    event_time_text: str
    session_index: int
    turn_index: int
    sentence_index: int
    speaker: str
    source_episode: str
    entities: tuple[str, ...]
    confidence: float = 0.7

    def metadata(self) -> dict[str, Any]:
        """Return JSON-serializable metadata for diagnostics and BM25."""
        return {
            "fact_id": self.fact_id,
            "valid_at": self.valid_at,
            "event_time_iso": self.event_time_iso,
            "event_time_text": self.event_time_text,
            "session_index": self.session_index,
            "turn_index": self.turn_index,
            "sentence_index": self.sentence_index,
            "speaker": self.speaker,
            "source_episode": self.source_episode,
            "entities": list(self.entities),
            "confidence": self.confidence,
        }


def extract_locomo_fact_records(sample_id: str, conversation: dict[str, Any], *, source_episode: str) -> list[LocomoFactRecord]:
    """Extract deterministic fact-like sentence records from a LoCoMo conversation."""
    from core.memory.rag.episode_time import apply_episode_heading_event_time
    from core.memory.retrieval.entity import extract_entities

    records: list[LocomoFactRecord] = []
    ignored_entities = _conversation_speaker_names(conversation)
    for session_index in _session_indices(conversation):
        turns = conversation.get(f"session_{session_index}")
        if not isinstance(turns, list):
            continue
        event_meta: dict[str, Any] = {}
        event_time_text = str(conversation.get(f"session_{session_index}_date_time", "") or "").strip()
        if event_time_text:
            apply_episode_heading_event_time(event_meta, f"## Session {session_index} - {event_time_text}")
        event_time_iso = str(event_meta.get("event_time_iso", "") or "")
        valid_at = event_time_iso

        for turn_index, turn in enumerate(turns):
            speaker, turn_text = _turn_speaker_and_text(turn)
            if not turn_text:
                continue
            for sentence_index, sentence in enumerate(_split_sentences(turn_text)):
                if len(sentence) < 2:
                    continue
                fact_text = f"{speaker}: {sentence}" if speaker else sentence
                entities = tuple(sorted(extract_entities(fact_text, ignored_entities=ignored_entities)))[:30]
                fact_id = _stable_fact_id(
                    sample_id,
                    session_index=session_index,
                    turn_index=turn_index,
                    sentence_index=sentence_index,
                    text=fact_text,
                )
                records.append(
                    LocomoFactRecord(
                        fact_id=fact_id,
                        text=fact_text,
                        valid_at=valid_at,
                        event_time_iso=event_time_iso,
                        event_time_text=event_time_text,
                        session_index=session_index,
                        turn_index=turn_index,
                        sentence_index=sentence_index,
                        speaker=speaker or "Unknown",
                        source_episode=source_episode,
                        entities=entities,
                    ),
                )
    return records


def write_fact_records(facts_dir: Path, records: list[LocomoFactRecord]) -> int:
    """Write fact records as markdown plus indexable JSONL and return newly written count."""
    facts_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for record in records:
        path = facts_dir / f"fact_{record.fact_id}.md"
        if path.exists():
            continue
        path.write_text(_render_fact_markdown(record), encoding="utf-8")
        written += 1
    jsonl_path = facts_dir / "locomo_facts.jsonl"
    if not jsonl_path.exists():
        jsonl_path.write_text(
            "\n".join(_to_core_fact_json_line(record) for record in records) + ("\n" if records else ""),
            encoding="utf-8",
        )
        written = max(written, len(records))
    return written


def fact_bm25_documents(records: list[LocomoFactRecord]) -> list[tuple[str, dict[str, Any]]]:
    """Build BM25 corpus rows for fact records."""
    documents: list[tuple[str, dict[str, Any]]] = []
    for record in records:
        metadata = {
            **record.metadata(),
            "memory_type": "facts",
            "source_file": f"facts/fact_{record.fact_id}.md",
            "section": 0,
            "chunk_index": 0,
        }
        if record.event_time_iso:
            try:
                metadata["valid_at"] = datetime.fromisoformat(record.event_time_iso).timestamp()
            except ValueError:
                pass
        documents.append((record.text, metadata))
    return documents


def _session_indices(conversation: dict[str, Any]) -> list[int]:
    indices: set[int] = set()
    for key in conversation:
        match = _SESSION_RE.match(key)
        if match:
            indices.add(int(match.group(1)))
    return sorted(indices)


def _conversation_speaker_names(conversation: dict[str, Any]) -> tuple[str, ...]:
    names = {
        str(conversation.get(key, "") or "").strip()
        for key in ("speaker_a", "speaker_b")
        if str(conversation.get(key, "") or "").strip()
    }
    return tuple(sorted(names))


def _turn_speaker_and_text(turn: Any) -> tuple[str, str]:
    if isinstance(turn, dict):
        speaker = str(turn.get("speaker", "") or "").strip() or "Unknown"
        text = str(turn.get("text", "") or "").strip()
        caption = str(turn.get("blip_caption", "") or "").strip()
        query = str(turn.get("query", "") or "").strip()
        extras: list[str] = []
        if caption:
            extras.append(f"Image caption: {caption}")
        if not text and query:
            extras.append(f"Image search: {query}")
        parts = [text, *extras]
        return speaker, _normalize_text(" ".join(part for part in parts if part))
    if isinstance(turn, (list, tuple)) and len(turn) >= 2:
        return str(turn[0]).strip() or "Unknown", _normalize_text(str(turn[1]))
    return "Unknown", ""


def _split_sentences(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(normalized) if part.strip()]
    if not parts:
        return []
    sentences: list[str] = []
    for part in parts:
        if len(part) <= 320:
            sentences.append(part)
            continue
        sentences.extend(_split_long_sentence(part))
    return sentences


def _split_long_sentence(text: str) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if current else 0)
        if current and projected > 320:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
            continue
        current.append(word)
        current_len = projected
    if current:
        chunks.append(" ".join(current))
    return chunks


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _stable_fact_id(
    sample_id: str,
    *,
    session_index: int,
    turn_index: int,
    sentence_index: int,
    text: str,
) -> str:
    raw = f"{sample_id}|{session_index}|{turn_index}|{sentence_index}|{text}"
    return sha1(raw.encode("utf-8")).hexdigest()[:16]


def _render_fact_markdown(record: LocomoFactRecord) -> str:
    metadata = record.metadata()
    frontmatter: list[str] = [
        "---",
        f"fact_id: {_yaml_scalar(record.fact_id)}",
        f"valid_from: {_yaml_scalar(record.valid_at)}",
        f"summary: {_yaml_scalar(record.text[:200])}",
        f"confidence: {record.confidence:.2f}",
        f"source_episode: {_yaml_scalar(record.source_episode)}",
        f"session_index: {record.session_index}",
        f"turn_index: {record.turn_index}",
        f"sentence_index: {record.sentence_index}",
        f"speaker: {_yaml_scalar(record.speaker)}",
        f"event_time_iso: {_yaml_scalar(record.event_time_iso)}",
        f"event_time_text: {_yaml_scalar(record.event_time_text)}",
        f"entities: {_yaml_scalar(json.dumps(metadata['entities'], ensure_ascii=False))}",
        "---",
        "",
        record.text,
        "",
    ]
    return "\n".join(frontmatter)


def _to_core_fact_json_line(record: LocomoFactRecord) -> str:
    from core.memory.facts import FactRecord

    entities = list(record.entities)
    speaker_key = record.speaker.casefold()
    target_entity = next((entity for entity in entities if entity.casefold() != speaker_key), "")
    fact = FactRecord(
        fact_id=record.fact_id,
        text=record.text,
        source_entity=record.speaker,
        target_entity=target_entity,
        edge_type="MENTIONS",
        raw_edge_type="locomo_sentence_fact",
        valid_at=record.valid_at,
        recorded_at=record.valid_at,
        entities=entities,
        source_episode=record.source_episode,
        source_session_id=str(record.session_index),
        confidence=record.confidence,
    )
    return fact.to_json_line()


def _yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
