from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Guard for direct Chroma opens that lack per-instance authorization."""


def require_direct_chroma_allowed() -> None:
    """Reject direct opens unless their call site passed explicit permission."""
    raise RuntimeError("Direct ChromaDB access is disabled; pass allow_direct=True for an explicitly authorized path.")
