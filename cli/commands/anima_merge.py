from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI handler for ``animaworks anima merge``."""

import argparse
import sys

from core.lifecycle.anima_merge import (
    AnimaMergeError,
    AnimaMergeFinalizeService,
    AnimaMergeService,
)
from core.paths import get_data_dir


def cmd_anima_merge(args: argparse.Namespace) -> None:
    """Dry-run or execute an Anima merge through its tombstone phase."""
    execute = bool(getattr(args, "execute", False))
    service = AnimaMergeService(
        get_data_dir(),
        args.source,
        args.target,
        gateway_url=getattr(args, "gateway_url", None) or "http://localhost:18500",
        force=bool(getattr(args, "force", False)),
    )
    try:
        result = service.run(execute=execute, resume=bool(getattr(args, "resume", False)))
    except AnimaMergeError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    mode = "execute" if execute else "dry-run"
    print(f"Anima merge {mode}: {result.source} → {result.target}")
    print(f"Manifest (JSON): {result.manifest_json}")
    print(f"Manifest (Markdown): {result.manifest_markdown}")
    if result.snapshot_path is not None:
        print(f"Snapshot: {result.snapshot_path}")
    if result.journal_path is not None:
        print(f"Journal: {result.journal_path}")
    if execute:
        print("Anima merge completed through VERIFY and source TOMBSTONE.")
        journal = result.journal_path
        if journal is not None:
            import json

            data = json.loads(journal.read_text(encoding="utf-8"))
            smoke = data.get("phases", {}).get("VERIFY", {}).get("artifacts", {}).get("smoke_check", {})
            if isinstance(smoke, dict) and smoke.get("manual_required"):
                print("Target smoke check: skipped offline; manual smoke check required.")


def cmd_anima_merge_finalize(args: argparse.Namespace) -> None:
    """Dry-run or explicitly finalize a completed Anima merge."""

    execute = bool(getattr(args, "execute", False))
    service = AnimaMergeFinalizeService(get_data_dir(), args.source, args.target)
    try:
        result = service.run(execute=execute, resume=bool(getattr(args, "resume", False)))
    except AnimaMergeError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    mode = "execute" if execute else "dry-run"
    print(f"Anima merge-finalize {mode}: {result.source} → {result.target}")
    print(f"Merge journal: {result.merge_journal_path}")
    print(f"Archive: {result.archive_path}")
    if result.journal_path is not None:
        print(f"Finalize journal: {result.journal_path}")
