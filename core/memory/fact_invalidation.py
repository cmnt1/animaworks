from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Temporal reconciliation for legacy atomic facts."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.memory.fact_invalidation_llm import classify_fact_relation as _classify_fact_relation
from core.memory.facts import (
    FactRecord,
    FactRecordUpdate,
    fact_entity_names,
    find_fact_record,
    is_fact_active,
    read_fact_records,
    update_fact_record_by_id,
    update_fact_records_and_append,
)
from core.time_utils import ensure_aware, now_iso

logger = logging.getLogger("animaworks.memory.fact_invalidation")

_ALLOWED_LABELS = {"CONTRADICT", "COMPLEMENT", "DUPLICATE", "ADD"}


class ReconcileAction(StrEnum):
    """Persistence action selected for a new legacy fact."""

    ADD = "ADD"
    SKIP = "SKIP"
    INVALIDATE_OLD = "INVALIDATE_OLD"
    UPDATE = "UPDATE"


@dataclass(frozen=True)
class FactCandidate:
    """A similar persisted fact candidate."""

    record: FactRecord
    score: float
    path: Path
    doc_id: str = ""


@dataclass(frozen=True)
class ReconcileConfig:
    """Runtime knobs for fact reconciliation."""

    enabled: bool = True
    threshold: float = 0.82
    top_k: int = 5


@dataclass(frozen=True)
class ReconcileResult:
    """Result of reconciling a new fact against persisted facts."""

    action: ReconcileAction
    fact: FactRecord
    should_append: bool
    label: str = ""
    reason: str = ""
    affected_fact_ids: tuple[str, ...] = ()
    affected_paths: tuple[Path, ...] = ()
    updated_records: tuple[FactRecord, ...] = ()
    appended_records: tuple[FactRecord, ...] = ()
    error: str = ""


FactClassifier = Callable[[FactRecord, list[FactCandidate], Path], str]
FactCandidateSearch = Callable[[Path, FactRecord, int], list[FactCandidate]]


@dataclass(frozen=True)
class CandidateLabelResult:
    labels: tuple[tuple[FactCandidate, str], ...] = ()
    error_reason: str = ""
    error: str = ""


def reconcile_new_fact(
    anima_dir: Path,
    fact: FactRecord,
    *,
    as_of_time: str | datetime | None = None,
    classifier: FactClassifier | None = None,
    candidate_search: FactCandidateSearch | None = None,
    config: ReconcileConfig | None = None,
) -> ReconcileResult:
    """Reconcile a new fact before append.

    Low similarity, Chroma unavailability, LLM failure, and malformed LLM
    labels all fall back to ADD so ingest remains non-destructive.
    """
    if not fact.text:
        return _result(ReconcileAction.SKIP, fact, should_append=False, reason="empty_fact")

    cfg = config or _load_reconcile_config()
    if not cfg.enabled:
        return _result(ReconcileAction.ADD, fact, should_append=True, reason="disabled")

    search = candidate_search or _search_fact_candidates
    try:
        candidates = search(Path(anima_dir), fact, cfg.top_k)
    except Exception as exc:
        logger.warning("Fact candidate search failed; adding fact without reconciliation", exc_info=True)
        return _result(
            ReconcileAction.ADD,
            fact,
            should_append=True,
            reason="candidate_search_failed",
            error=str(exc),
        )

    if not candidates:
        return _result(ReconcileAction.ADD, fact, should_append=True, reason="no_candidates")

    effective_time = _fact_effective_time(fact, as_of_time)
    active = [candidate for candidate in candidates if is_fact_active(candidate.record, as_of_time=effective_time)]
    if not active:
        return _result(ReconcileAction.ADD, fact, should_append=True, reason="no_active_candidates")

    above_threshold = [candidate for candidate in active if candidate.score >= cfg.threshold]
    if not above_threshold:
        return _result(ReconcileAction.ADD, fact, should_append=True, reason="below_similarity_threshold")

    labels_result = _classify_candidate_labels(
        fact,
        above_threshold,
        Path(anima_dir),
        classifier or _classify_fact_relation,
    )
    if labels_result.error_reason:
        return _result(
            ReconcileAction.ADD,
            fact,
            should_append=True,
            reason=labels_result.error_reason,
            error=labels_result.error,
        )

    contradictions = [candidate for candidate, label in labels_result.labels if label == "CONTRADICT"]
    duplicates = [candidate for candidate, label in labels_result.labels if label == "DUPLICATE"]
    if contradictions:
        return _apply_contradictions(
            Path(anima_dir),
            fact,
            contradictions,
            effective_time,
            label="CONTRADICT",
            append_fact=not duplicates,
        )

    if duplicates:
        best = max(duplicates, key=lambda candidate: candidate.score)
        return _result(
            ReconcileAction.SKIP,
            fact,
            should_append=False,
            label="DUPLICATE",
            reason="duplicate",
            affected_fact_ids=(best.record.fact_id,),
        )

    complements = [candidate for candidate, label in labels_result.labels if label == "COMPLEMENT"]
    if complements:
        return _apply_complement(Path(anima_dir), fact, complements, label="COMPLEMENT")

    return _result(ReconcileAction.ADD, fact, should_append=True, label="ADD", reason="classified_add")


def _load_reconcile_config() -> ReconcileConfig:
    try:
        from core.config import load_config

        rag = load_config().rag
        threshold = float(getattr(rag, "facts_reconcile_similarity_threshold", 0.82))
        top_k = int(getattr(rag, "facts_reconcile_top_k", 5))
        return ReconcileConfig(
            enabled=bool(getattr(rag, "facts_reconcile_enabled", True)),
            threshold=max(0.0, min(1.0, threshold)),
            top_k=max(1, top_k),
        )
    except Exception:
        logger.debug("Using default fact reconcile config", exc_info=True)
        return ReconcileConfig()


def _search_fact_candidates(anima_dir: Path, fact: FactRecord, top_k: int) -> list[FactCandidate]:
    from core.memory.rag.singleton import generate_embeddings, get_vector_store

    vector_store = get_vector_store(anima_dir.name)
    if vector_store is None:
        return []
    embeddings = generate_embeddings([fact.text], purpose="query")
    if not embeddings:
        return []

    results = vector_store.query(
        collection=f"{anima_dir.name}_facts",
        embedding=embeddings[0],
        top_k=top_k,
    )
    candidates: list[FactCandidate] = []
    seen: set[str] = set()
    for result in results:
        metadata = result.document.metadata or {}
        fact_id = str(metadata.get("fact_id", "") or "").strip()
        if not fact_id or fact_id in seen:
            continue
        location = _find_fact_record_from_metadata(anima_dir, fact_id, metadata)
        if location is None:
            continue
        seen.add(fact_id)
        candidates.append(
            FactCandidate(
                record=location.record,
                score=float(result.score),
                path=location.path,
                doc_id=result.document.id,
            )
        )
    return candidates


def _find_fact_record_from_metadata(
    anima_dir: Path,
    fact_id: str,
    metadata: dict[str, Any],
) -> FactRecordUpdate | None:
    source_file = str(metadata.get("source_file", "") or "").strip()
    if source_file:
        source_path = Path(source_file)
        path = source_path if source_path.is_absolute() else anima_dir / source_path
        try:
            path.resolve().relative_to(anima_dir.resolve())
        except ValueError:
            path = None
        if path is not None and path.is_file():
            records = read_fact_records(path, include_expired=True)
            for idx, record in enumerate(records, 1):
                if record.fact_id == fact_id:
                    return FactRecordUpdate(path=path, line_no=idx, record=record)
    return find_fact_record(anima_dir, fact_id)


def _classify_candidate_labels(
    fact: FactRecord,
    candidates: list[FactCandidate],
    anima_dir: Path,
    classify: FactClassifier,
) -> CandidateLabelResult:
    labels: list[tuple[FactCandidate, str]] = []
    for candidate in candidates:
        if candidate.record.fact_id == fact.fact_id or candidate.record.dedup_key == fact.dedup_key:
            labels.append((candidate, "DUPLICATE"))
            continue
        try:
            label = _parse_label(classify(fact, [candidate], anima_dir))
        except Exception as exc:
            logger.warning("Fact relation classification failed; adding fact", exc_info=True)
            return CandidateLabelResult(error_reason="classifier_failed", error=str(exc))
        if not label:
            logger.warning("Fact relation classifier returned invalid label; adding fact")
            return CandidateLabelResult(error_reason="invalid_label")
        labels.append((candidate, label))
    return CandidateLabelResult(labels=tuple(labels))


def _apply_contradictions(
    anima_dir: Path,
    fact: FactRecord,
    candidates: list[FactCandidate],
    invalidation_time: str,
    *,
    label: str,
    append_fact: bool = True,
) -> ReconcileResult:
    candidate_by_id = {candidate.record.fact_id: candidate for candidate in candidates}

    def make_updater(candidate: FactCandidate) -> Callable[[FactRecord], FactRecord | None]:
        def updater(current: FactRecord) -> FactRecord:
            if not _should_update_valid_until(current.valid_until, invalidation_time):
                return current
            return _record_with(current, valid_until=invalidation_time)

        return updater

    try:
        stored, updates = update_fact_records_and_append(
            anima_dir,
            {candidate.record.fact_id: make_updater(candidate) for candidate in candidates if candidate.record.fact_id},
            [fact] if append_fact else [],
            update_paths=[candidate.path for candidate in candidates],
        )
    except Exception as exc:
        logger.warning("Failed to persist fact invalidation; skipping new fact append", exc_info=True)
        return _result(
            ReconcileAction.SKIP,
            fact,
            should_append=False,
            label=label,
            reason="invalidate_failed",
            affected_fact_ids=tuple(candidate_by_id),
            affected_paths=tuple(sorted({candidate.path for candidate in candidates})),
            error=str(exc),
        )

    if len(updates) < len(candidate_by_id):
        missing = sorted(set(candidate_by_id) - {update.record.fact_id for update in updates})
        return _result(
            ReconcileAction.SKIP,
            fact,
            should_append=False,
            label=label,
            reason="invalidate_incomplete",
            affected_fact_ids=tuple(candidate_by_id),
            affected_paths=tuple(sorted({candidate.path for candidate in candidates})),
            error=f"missing updates for: {', '.join(missing)}",
        )

    return _result(
        ReconcileAction.INVALIDATE_OLD,
        fact,
        should_append=False,
        label=label,
        reason="contradiction",
        affected_fact_ids=tuple(update.record.fact_id for update in updates),
        affected_paths=tuple(sorted({update.path for update in updates})),
        updated_records=tuple(update.record for update in updates),
        appended_records=tuple(stored),
    )


def _apply_complement(
    anima_dir: Path,
    fact: FactRecord,
    candidates: list[FactCandidate],
    *,
    label: str,
) -> ReconcileResult:
    best = max(candidates, key=lambda candidate: candidate.score)
    try:
        update = update_fact_record_by_id(
            anima_dir,
            best.record.fact_id,
            lambda current: _merge_complement(current, fact),
            path=best.path,
        )
    except Exception as exc:
        logger.warning("Failed to persist complementary fact update; adding new fact", exc_info=True)
        return _result(
            ReconcileAction.ADD,
            fact,
            should_append=True,
            label=label,
            reason="complement_update_failed",
            affected_fact_ids=(best.record.fact_id,),
            affected_paths=(best.path,),
            error=str(exc),
        )

    if update is None:
        return _result(
            ReconcileAction.ADD,
            fact,
            should_append=True,
            label=label,
            reason="complement_target_missing",
            affected_fact_ids=(best.record.fact_id,),
            affected_paths=(best.path,),
        )

    return _result(
        ReconcileAction.UPDATE,
        fact,
        should_append=False,
        label=label,
        reason="complement",
        affected_fact_ids=(update.record.fact_id,),
        affected_paths=(update.path,),
        updated_records=(update.record,),
    )


def _merge_complement(old: FactRecord, new: FactRecord) -> FactRecord:
    text = old.text
    if new.text and new.text.casefold() not in old.text.casefold():
        text = f"{old.text} {new.text}".strip()
    return _record_with(
        old,
        text=text,
        source_entity=old.source_entity or new.source_entity,
        target_entity=old.target_entity or new.target_entity,
        edge_type=old.edge_type if old.edge_type != "RELATES_TO" else new.edge_type,
        raw_edge_type=old.raw_edge_type or new.raw_edge_type,
        valid_at=old.valid_at or new.valid_at,
        entities=_unique_strings([*fact_entity_names(old), *fact_entity_names(new)]),
        confidence=max(old.confidence, new.confidence),
    )


def _record_with(record: FactRecord, **updates: Any) -> FactRecord:
    data = record.to_dict()
    data.update(updates)
    return FactRecord.from_dict(data)


def _should_update_valid_until(current_valid_until: str, invalidation_time: str) -> bool:
    if not str(current_valid_until or "").strip():
        return True
    current_dt = _parse_datetime(current_valid_until)
    invalidation_dt = _parse_datetime(invalidation_time)
    if current_dt is None or invalidation_dt is None:
        return False
    return invalidation_dt < current_dt


def _fact_effective_time(fact: FactRecord, as_of_time: str | datetime | None) -> str:
    if fact.valid_at:
        return fact.valid_at
    if fact.recorded_at:
        return fact.recorded_at
    if isinstance(as_of_time, datetime):
        return ensure_aware(as_of_time).isoformat()
    if str(as_of_time or "").strip():
        return str(as_of_time)
    return now_iso()


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return ensure_aware(value)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _parse_label(text: str) -> str:
    clean = str(text or "").strip().strip('"').strip("'").upper()
    return clean if clean in _ALLOWED_LABELS else ""


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _result(
    action: ReconcileAction,
    fact: FactRecord,
    *,
    should_append: bool,
    label: str = "",
    reason: str = "",
    affected_fact_ids: tuple[str, ...] = (),
    affected_paths: tuple[Path, ...] = (),
    updated_records: tuple[FactRecord, ...] = (),
    appended_records: tuple[FactRecord, ...] = (),
    error: str = "",
) -> ReconcileResult:
    return ReconcileResult(
        action=action,
        fact=fact,
        should_append=should_append,
        label=label,
        reason=reason,
        affected_fact_ids=affected_fact_ids,
        affected_paths=affected_paths,
        updated_records=updated_records,
        appended_records=appended_records,
        error=error,
    )
