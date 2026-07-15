from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI handler for ``animaworks anima merge``."""

import argparse
import sys

from core.lifecycle.anima_merge import AnimaMergeError, AnimaMergeService
from core.paths import get_data_dir


def cmd_anima_merge(args: argparse.Namespace) -> None:
    """Dry-run or execute Phase 1 of an Anima merge."""
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
        print("Phase 1 merge completed. Later phases remain intentionally deferred.")
