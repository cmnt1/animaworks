# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Stage implementations for the egress pipeline.

Each stage either transforms the answer facts, or raises :class:`EgressStageError`
whose ``reason`` (a stable, data-free category) makes the pipeline fail closed.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from core.enclave.egress.config import CommandStage, MaskerStage, PseudonymizeStage, RegexDenylistStage, Stage
from core.enclave.egress.fs import ensure_dir_0700
from core.enclave.egress.masker import MaskerUnavailableError, mask_text
from core.enclave.egress.models import Fact
from core.platform.atomic_io import atomic_write_json


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
    if isinstance(stage, MaskerStage):
        return _run_masker(stage, facts)
    if isinstance(stage, RegexDenylistStage):
        return _run_regex_denylist(stage, facts)
    if isinstance(stage, CommandStage):
        return _run_command(stage, facts)
    raise EgressStageError("unknown_stage")
