from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Capability guard for native Chroma access owned by a single process."""


class _DirectAccessCapability:
    """Unforgeable-by-value marker for explicitly authorized direct access."""

    __slots__ = ()


OWNER_CAPABILITY = _DirectAccessCapability()


def require_direct_chroma_allowed(capability: _DirectAccessCapability | None) -> None:
    """Reject direct opens unless the caller passes the owner capability object."""
    if capability is not OWNER_CAPABILITY:
        raise RuntimeError(
            "Direct ChromaDB access is disabled; pass the owner capability (OWNER_CAPABILITY) for an authorized path."
        )
