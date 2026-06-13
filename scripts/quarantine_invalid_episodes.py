#!/usr/bin/env python
from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Quarantine episode files whose filename date predates system launch.

Dry-run is the default. Pass ``--execute`` to move matching files from
``episodes/`` to ``archive/invalid-dates/`` for each anima.
"""

import argparse
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DEFAULT_LAUNCH_DATE = date(2026, 2, 1)


@dataclass(frozen=True)
class QuarantineCandidate:
    anima_name: str
    source: Path
    destination: Path
    episode_date: date


def _episode_file_date(path: Path) -> date | None:
    stem = path.stem
    if len(stem) < 10:
        return None
    try:
        return datetime.strptime(stem[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _iter_anima_dirs(data_dir: Path, anima_names: Sequence[str]) -> list[Path]:
    animas_dir = data_dir / "animas"
    if anima_names:
        return [animas_dir / name for name in anima_names]
    if not animas_dir.is_dir():
        return []
    return sorted(path for path in animas_dir.iterdir() if path.is_dir())


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def find_invalid_episode_candidates(
    data_dir: Path,
    *,
    launch_date: date,
    anima_names: Sequence[str] = (),
) -> list[QuarantineCandidate]:
    """Find episode files dated before *launch_date* by filename."""
    candidates: list[QuarantineCandidate] = []
    for anima_dir in _iter_anima_dirs(data_dir, anima_names):
        episodes_dir = anima_dir / "episodes"
        if not episodes_dir.is_dir():
            continue
        archive_dir = anima_dir / "archive" / "invalid-dates"
        for episode_file in sorted(path for path in episodes_dir.iterdir() if path.is_file()):
            episode_date = _episode_file_date(episode_file)
            if episode_date is None or episode_date >= launch_date:
                continue
            destination = _unique_destination(archive_dir / episode_file.name)
            candidates.append(
                QuarantineCandidate(
                    anima_name=anima_dir.name,
                    source=episode_file,
                    destination=destination,
                    episode_date=episode_date,
                )
            )
    return candidates


def quarantine_candidates(candidates: Sequence[QuarantineCandidate], *, execute: bool) -> int:
    """Print candidate actions and optionally move files."""
    moved = 0
    action = "MOVE" if execute else "DRY-RUN"
    for candidate in candidates:
        display_root = candidate.source.parents[2]
        print(
            f"{action} {candidate.anima_name}: "
            f"{candidate.source.relative_to(display_root)} -> "
            f"{candidate.destination.relative_to(display_root)}"
        )
        if not execute:
            continue
        candidate.destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(candidate.source), str(candidate.destination))
        moved += 1
    return moved


def _parse_date(raw: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _default_data_dir() -> Path:
    try:
        from core.paths import get_data_dir

        return get_data_dir()
    except Exception:
        return Path.home() / ".animaworks"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Quarantine episode files whose filename date predates system launch.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=_default_data_dir(),
        help="AnimaWorks runtime data directory; defaults to ANIMAWORKS_DATA_DIR or ~/.animaworks.",
    )
    parser.add_argument(
        "--anima",
        action="append",
        default=[],
        help="Limit scan to one anima. Can be passed multiple times. Defaults to all animas.",
    )
    parser.add_argument(
        "--launch-date",
        type=_parse_date,
        default=DEFAULT_LAUNCH_DATE,
        help="Earliest valid episode date in YYYY-MM-DD format. Default: 2026-02-01.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Move matching files. Without this flag, only print the dry-run plan.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    data_dir = args.data_dir.expanduser().resolve()
    candidates = find_invalid_episode_candidates(
        data_dir,
        launch_date=args.launch_date,
        anima_names=args.anima,
    )
    moved = quarantine_candidates(candidates, execute=args.execute)
    print(
        f"summary: data_dir={data_dir} launch_date={args.launch_date.isoformat()} "
        f"candidates={len(candidates)} moved={moved} dry_run={not args.execute}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
