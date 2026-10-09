# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Stage implementations for the egress pipeline.

Each stage either transforms the answer facts, or raises :class:`EgressStageError`
whose ``reason`` (a stable, data-free category) makes the pipeline fail closed.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

from core.enclave.egress.config import (
    CommandStage,
    KnownValuesStage,
    MaskerStage,
    PseudonymizeStage,
    RegexDenylistStage,
    Stage,
)
from core.enclave.egress.fs import ensure_dir_0700
from core.enclave.egress.masker import MaskerUnavailableError, mask_text
from core.enclave.egress.masker.facts import _kata_to_hira, normalize_known_value
from core.enclave.egress.models import Fact
from core.platform.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)


class EgressStageError(Exception):
    """A stage failed; the pipeline must fail closed with ``reason``."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _map_facts(facts: list[Fact], fn: Any) -> tuple[list[Fact], int]:
    """Apply *fn(text) -> (new_text, count)* to every fact and evidence.

    Returns the transformed facts plus the total replacement count.
    """
    new_facts: list[Fact] = []
    total = 0
    for fact in facts:
        text, count = fn(fact.fact)
        total += count
        evidence: list[str] = []
        for item in fact.evidence:
            new_item, item_count = fn(item)
            total += item_count
            evidence.append(new_item)
        new_facts.append(Fact(fact=text, evidence=evidence))
    return new_facts, total


# ---------------------------------------------------------------------------
# pseudonymize_ids
# ---------------------------------------------------------------------------

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PSEUDONYM_NUM_RE = re.compile(r"^([A-Za-z0-9]+)-(\d+)$")


def _next_counter(mapping: dict[str, str], prefix: str) -> int:
    highest = 0
    for value in mapping.values():
        m = _PSEUDONYM_NUM_RE.match(value)
        if m and m.group(1) == prefix:
            highest = max(highest, int(m.group(2)))
    return highest + 1


def _run_pseudonymize(
    stage: PseudonymizeStage,
    facts: list[Fact],
    *,
    data_dir: Path,
    case_id: str,
) -> tuple[list[Fact], int]:
    if not _CASE_ID_RE.match(case_id):
        raise EgressStageError("invalid_case_id")

    base = ensure_dir_0700(data_dir / "enclave" / "pseudonyms")
    map_path = base / f"{case_id}.json"

    mapping: dict[str, str] = {}
    if map_path.exists():
        try:
            loaded = json.loads(map_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                mapping = {str(k): str(v) for k, v in loaded.items()}
        except Exception as exc:
            raise EgressStageError("pseudonym_map_corrupt") from exc

    def _apply_patterns(text: str) -> tuple[str, int]:
        count = 0
        for pattern in stage.patterns:
            rx = re.compile(pattern.regex)
            prefix = pattern.prefix
            counter = _next_counter(mapping, prefix)

            def _repl(match: re.Match, _prefix: str = prefix) -> str:
                nonlocal counter, count
                value = match.group(0)
                pseudonym = mapping.get(value)
                if pseudonym is None:
                    pseudonym = f"{_prefix}-{counter:03d}"
                    counter += 1
                    mapping[value] = pseudonym
                count += 1
                return pseudonym

            text = rx.sub(_repl, text)
        return text, count

    new_facts, total = _map_facts(facts, _apply_patterns)
    atomic_write_json(map_path, mapping, mode=0o600, ensure_ascii=False)
    return new_facts, total


# ---------------------------------------------------------------------------
# known_values
# ---------------------------------------------------------------------------


def _normalize_known(value: str) -> str:
    """Normalize a known value for matching (shared with the masker module)."""
    return normalize_known_value(value)


def _known_variants(raw: str, min_length: int, ngram: int):
    norm = _normalize_known(raw)
    if len(norm) < min_length or not norm:
        return
    # A value longer than the n-gram is fully covered by its overlapping n-grams,
    # and overlapping spans merge, so the whole value adds no redaction. Skipping
    # it keeps the number of distinct match lengths small for long free text.
    if not (ngram > 0 and len(norm) > ngram):
        yield norm
    if len(norm) >= ngram and ngram > 0:
        for i in range(len(norm) - ngram + 1):
            yield norm[i : i + ngram]


def _add_known(known: set[str], raw: str, min_length: int, ngram: int) -> None:
    """Compatibility helper that expands a raw value into a flat known set."""
    known.update(_known_variants(raw, min_length, ngram))


def _add_known_buckets(known: dict[int, set[str]], raw: str, min_length: int, ngram: int) -> None:
    """Add normalized variants to buckets keyed by their exact match length."""
    for value in _known_variants(raw, min_length, ngram):
        known.setdefault(len(value), set()).add(value)


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("records", "data", "items"):
            if isinstance(raw.get(key), list):
                return [r for r in raw[key] if isinstance(r, dict)]
        return []
    return []


def _collect_source_values(record: dict[str, Any], fields: list[str], out: list[str]) -> None:
    if fields:
        for field in fields:
            value = record.get(field)
            if isinstance(value, str):
                out.append(value)
    else:
        for value in record.values():
            if isinstance(value, str):
                out.append(value)


def _read_source_values(path: Path, fmt: str, fields: list[str]) -> list[str]:
    values: list[str] = []
    if fmt == "jsonl":
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if isinstance(record, dict):
                    _collect_source_values(record, fields, values)
    elif fmt == "csv":
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            for record in reader:
                if record is None:
                    continue
                _collect_source_values(record, fields, values)
    elif fmt == "json":
        for record in _load_json_records(path):
            _collect_source_values(record, fields, values)
    else:
        raise EgressStageError("known_values_bad_format")
    return values


def _run_known_values(
    stage: KnownValuesStage,
    facts: list[Fact],
    *,
    data_dir: Path,
) -> tuple[list[Fact], int]:
    min_length = stage.min_length
    ngram = stage.ngram
    known: dict[int, set[str]] = {}

    for source in stage.sources:
        path = data_dir / source.path
        if not path.exists():
            raise EgressStageError("known_values_source_missing")
        for value in _read_source_values(path, source.format, source.fields):
            _add_known_buckets(known, value, min_length, ngram)

    ledger_path = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    if ledger_path.exists():
        with ledger_path.open(encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    # A skipped line could hide a value that must be redacted.
                    raise EgressStageError("known_values_ledger_corrupt") from exc
                value = record.get("value") if isinstance(record, dict) else None
                if isinstance(value, str):
                    _add_known_buckets(known, value, min_length, ngram)

    if not known:
        return facts, 0

    def _redact(text: str) -> tuple[str, int]:
        return _redact_known_patterns(text, known)

    new_facts, total = _map_facts(facts, _redact)
    return new_facts, total


def _normalize_with_positions(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    positions: list[int] = []
    for idx, ch in enumerate(text):
        for norm in unicodedata.normalize("NFKC", ch):
            if norm.isspace():
                continue
            chars.append(_kata_to_hira(norm).lower())
            positions.append(idx)
    return "".join(chars), positions


def _redact_known_patterns(text: str, known: dict[int, set[str]]) -> tuple[str, int]:
    """Find known values without building one enormous regular expression.

    The longest matching value is selected at every normalized character
    position, matching the ordered alternation used by the former regex path.
    The resulting source spans are merged with the same overlap/touch rule.
    """
    normalized, positions = _normalize_with_positions(text)
    if not normalized:
        return text, 0

    lengths = sorted((length for length in known if length > 0), reverse=True)
    if not lengths:
        return text, 0

    spans: list[tuple[int, int]] = []
    text_length = len(normalized)
    for start in range(text_length):
        remaining = text_length - start
        for length in lengths:
            if length > remaining:
                continue
            if normalized[start : start + length] in known[length]:
                spans.append((positions[start], positions[start + length - 1] + 1))
                break

    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    if not merged:
        return text, 0

    out: list[str] = []
    last = 0
    for start, end in merged:
        out.append(text[last:start])
        out.append("[REDACTED]")
        last = end
    out.append(text[last:])
    return "".join(out), len(merged)


def _redact_known(text: str, regex: re.Pattern) -> tuple[str, int]:
    """Legacy regex implementation retained for differential regression tests."""
    normalized, positions = _normalize_with_positions(text)
    if not normalized:
        return text, 0

    spans: list[tuple[int, int]] = []
    for match in regex.finditer(normalized):
        ns, ne = match.span(1)
        if ns >= ne:
            continue
        spans.append((positions[ns], positions[ne - 1] + 1))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    if not merged:
        return text, 0

    out: list[str] = []
    last = 0
    for start, end in merged:
        out.append(text[last:start])
        out.append("[REDACTED]")
        last = end
    out.append(text[last:])
    return "".join(out), len(merged)


# ---------------------------------------------------------------------------
# masker
# ---------------------------------------------------------------------------


def _run_masker(stage: MaskerStage, facts: list[Fact]) -> tuple[list[Fact], int]:
    profile = stage.profile

    def _mask(text: str) -> tuple[str, int]:
        try:
            masked = mask_text(profile, text)
        except MaskerUnavailableError as exc:
            raise EgressStageError("masker_unavailable") from exc
        except Exception as exc:
            raise EgressStageError("masker_failed") from exc
        return masked, masked.count("[MASK")

    return _map_facts(facts, _mask)


# ---------------------------------------------------------------------------
# regex_denylist
# ---------------------------------------------------------------------------


def _run_regex_denylist(stage: RegexDenylistStage, facts: list[Fact]) -> tuple[list[Fact], int]:
    compiled = [(re.compile(p.regex), p.action) for p in stage.patterns]

    def _apply(text: str) -> tuple[str, int]:
        count = 0
        for rx, action in compiled:
            if action == "block":
                if rx.search(text):
                    raise EgressStageError("denylist_match")
                continue
            new_text, n = rx.subn("[REDACTED]", text)
            count += n
            text = new_text
        return text, count

    return _map_facts(facts, _apply)


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------


def _parse_result_facts(result: Any) -> list[Fact]:
    if not isinstance(result, dict):
        raise EgressStageError("command_invalid_structure")
    items = result.get("facts")
    if not isinstance(items, list):
        raise EgressStageError("command_invalid_structure")
    facts: list[Fact] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("fact"), str):
            raise EgressStageError("command_invalid_structure")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
            raise EgressStageError("command_invalid_structure")
        facts.append(Fact(fact=item["fact"], evidence=list(evidence)))
    return facts


def _run_command(stage: CommandStage, facts: list[Fact]) -> tuple[list[Fact], int]:
    payload = {"facts": [{"fact": f.fact, "evidence": f.evidence} for f in facts]}
    data = json.dumps(payload, ensure_ascii=False)
    try:
        proc = subprocess.run(
            list(stage.argv),
            input=data,
            capture_output=True,
            text=True,
            timeout=float(stage.timeout_s),
        )
    except subprocess.TimeoutExpired as exc:
        raise EgressStageError("command_timeout") from exc
    except OSError as exc:
        raise EgressStageError("command_spawn_failed") from exc

    if proc.returncode != 0:
        raise EgressStageError("command_nonzero_exit")

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise EgressStageError("command_invalid_json") from exc

    return _parse_result_facts(result), 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def run_stage(
    stage: Stage,
    facts: list[Fact],
    *,
    data_dir: Path,
    case_id: str,
) -> tuple[list[Fact], int]:
    """Run one configured stage over *facts* and return (new_facts, count)."""
    if isinstance(stage, PseudonymizeStage):
        return _run_pseudonymize(stage, facts, data_dir=data_dir, case_id=case_id)
    if isinstance(stage, KnownValuesStage):
        return _run_known_values(stage, facts, data_dir=data_dir)
    if isinstance(stage, MaskerStage):
        return _run_masker(stage, facts)
    if isinstance(stage, RegexDenylistStage):
        return _run_regex_denylist(stage, facts)
    if isinstance(stage, CommandStage):
        return _run_command(stage, facts)
    raise EgressStageError("unknown_stage")
