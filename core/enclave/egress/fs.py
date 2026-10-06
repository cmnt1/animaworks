# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Small filesystem helpers enforcing enclave file/directory permissions.

Masking state and audit records contain personal data, so directories are
created with mode 0700 and data files with mode 0600 regardless of the
process umask.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_UMASK = 0o077


def _apply_umask(mode: int) -> int:
    return mode & ~_UMASK


def ensure_dir_0700(path: Path) -> Path:
    """Create *path* (and parents) with mode 0700 and return it."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, _apply_umask(0o700))
    return path


def ensure_file_0600(path: Path) -> Path:
    """Ensure *path* exists with mode 0600 and return it."""
    path.touch(exist_ok=True)
    os.chmod(path, _apply_umask(0o600))
    return path
