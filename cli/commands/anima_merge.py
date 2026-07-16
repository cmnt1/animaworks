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
    """Dry-run or execute implemented phases of an Anima merge."""
    execute = bool(getattr(args, "execute", False))
    temp_worker = None
    if execute:
        from cli.commands.index_cmd import (
            _setup_offline_vector_worker_if_needed,
            _setup_server_delegation,
            _stop_offline_vector_worker,
        )

        server_mode = _setup_server_delegation()
        temp_worker = _setup_offline_vector_worker_if_needed(server_mode)
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
    finally:
        if execute:
            _stop_offline_vector_worker(temp_worker)

    mode = "execute" if execute else "dry-run"
    print(f"Anima merge {mode}: {result.source} → {result.target}")
    print(f"Manifest (JSON): {result.manifest_json}")
    print(f"Manifest (Markdown): {result.manifest_markdown}")
    if result.snapshot_path is not None:
        print(f"Snapshot: {result.snapshot_path}")
    if result.journal_path is not None:
        print(f"Journal: {result.journal_path}")
    if execute:
        print("Memory merge, reference rewrite, and target index rebuild completed. VERIFY/TOMBSTONE remain deferred.")
