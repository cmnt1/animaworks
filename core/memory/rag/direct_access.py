from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Direct ChromaDB access guard for approved production owners."""

import os

DIRECT_CHROMA_ENV = "ANIMAWORKS_ALLOW_DIRECT_CHROMA"

# Process-local grant. Kept OUT of os.environ: writing the grant into the
# environment leaks it to every child process (cron bash commands, task
# runners, CLI tools), and a child opening+closing the same chroma.sqlite3
# deletes its WAL, stranding the owner's live connections on deleted-WAL fds
# ("file is not a database" storms; 2026-08-11 incident). Subprocesses that
# legitimately need native chroma (vector worker, repair staging) either call
# enable_direct_chroma_for_process() themselves or receive the env var
# explicitly from their spawner.
_process_allowed = False


def direct_chroma_allowed() -> bool:
    """Return whether this process may instantiate native ChromaDB."""
    return _process_allowed or os.environ.get(DIRECT_CHROMA_ENV) == "1"


def require_direct_chroma_allowed() -> None:
    """Raise when native ChromaDB is requested outside the vector worker."""
    if direct_chroma_allowed():
        return
    raise RuntimeError(
        "Direct ChromaDB access is disabled outside an approved owner. "
        f"Set {DIRECT_CHROMA_ENV}=1 only for vector-worker, anima root, or explicit test processes."
    )


def enable_direct_chroma_for_process() -> None:
    """Mark the current process as an allowed native ChromaDB owner."""
    global _process_allowed
    _process_allowed = True
