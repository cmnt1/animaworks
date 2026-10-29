from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Split atomic facts that were grown by COMPLEMENT concatenation.

Until 2026-10-06 a COMPLEMENT reconcile label appended the new fact's text to
the existing record as ``f"{old} {new}"``. Japanese facts end with ``。``, so
every join left a ``。 `` seam. This migration splits active records at those
seams: the first piece stays in the original record (same fact_id), every other
piece becomes its own record, and pieces whose text already exists as an
active fact of the same Anima are dropped.

Dry-run by default. After ``--apply``, re-index the touched Animas with
``animaworks index --anima NAME`` so the facts collection drops the blobs.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_SEAM = "。 "


@dataclass
class SplitStats:
    records_split: int = 0
    pieces_added: int = 0
    pieces_dropped_duplicate: int = 0
    files_changed: int = 0


def split_text(text: str) -> list[str]:
    """Return the original fact texts joined into *text* (one item if unmerged)."""
    parts = [part.strip() for part in text.split(_SEAM)]
    pieces = [f"{part}。" for part in parts[:-1] if part] + ([parts[-1]] if parts and parts[-1] else [])
    return pieces if len(pieces) > 1 else [text]


def _entities_in(text: str, names: list[str]) -> list[str]:
    lowered = text.casefold()
    return [name for name in names if name and name.casefold() in lowered]


def _split_record(record, known_texts: set[str], stats: SplitStats) -> list:
    from core.memory.facts.store import FactRecord, fact_entity_names

    pieces = split_text(record.text)
    if len(pieces) == 1:
        return [record]

    names = fact_entity_names(record)
    first, rest = pieces[0], pieces[1:]
    head = record.to_dict()
    head.update(text=first, entities=_entities_in(first, names) or names)
    out = [FactRecord.from_dict(head)]
    known_texts.add(first.casefold())

    for piece in rest:
        key = piece.casefold()
        if key in known_texts:
            stats.pieces_dropped_duplicate += 1
            continue
        known_texts.add(key)
        entities = _entities_in(piece, names)
        out.append(
            FactRecord(
                text=piece,
                source_entity=record.source_entity if record.source_entity in entities else "",
                target_entity=record.target_entity if record.target_entity in entities else "",
                valid_at=record.valid_at,
                recorded_at=record.recorded_at,
                entities=entities,
                source_episode=record.source_episode,
                source_session_id=record.source_session_id,
                confidence=record.confidence,
            )
        )
        stats.pieces_added += 1
    stats.records_split += 1
    return out


def split_anima_facts(anima_dir: Path, *, apply: bool) -> SplitStats:
    from core.memory.facts.store import (
        _locked_file,
        _write_fact_records_unlocked,
        facts_dir,
        iter_active_fact_records,
        read_fact_records,
    )

    stats = SplitStats()
    directory = facts_dir(anima_dir)
    if not directory.is_dir():
        return stats
    known_texts = {record.text.casefold() for record in iter_active_fact_records(anima_dir)}

    for path in sorted(directory.glob("*.jsonl")):
        with _locked_file(path):
            records = read_fact_records(path, include_expired=True)
            rewritten = []
            changed = False
            for record in records:
                if not record.is_active() or _SEAM not in record.text:
                    rewritten.append(record)
                    continue
                split = _split_record(record, known_texts, stats)
                changed = changed or len(split) > 1 or split[0].text != record.text
                rewritten.extend(split)
            if changed:
                stats.files_changed += 1
                if apply:
                    _write_fact_records_unlocked(path, rewritten)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=None, help="runtime data dir (default: ANIMAWORKS_DATA_DIR)")
    parser.add_argument("--anima", action="append", default=[], help="limit to this Anima (repeatable)")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args(argv)

    data_dir = args.data_dir or Path(os.environ.get("ANIMAWORKS_DATA_DIR", "~/.animaworks")).expanduser()
    animas_dir = data_dir / "animas"
    names = args.anima or sorted(path.name for path in animas_dir.iterdir() if (path / "facts").is_dir())
    for name in names:
        stats = split_anima_facts(animas_dir / name, apply=args.apply)
        if stats.records_split:
            print(
                f"{name}: records_split={stats.records_split} pieces_added={stats.pieces_added} "
                f"pieces_dropped_duplicate={stats.pieces_dropped_duplicate} files_changed={stats.files_changed}"
            )
    if not args.apply:
        print("dry-run: no files written (pass --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
