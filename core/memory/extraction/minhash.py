# Copyright 2026 AnimaWorks
# Licensed under the Apache License, Version 2.0
"""MinHash-based approximate Jaccard similarity for entity deduplication."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────

NUM_PERM = 128


# ── Public API ─────────────────────────────────────────────


def minhash_signature(text: str, *, num_perm: int = NUM_PERM):
    """Create a MinHash signature from text (character 3-grams).

    Returns None if datasketch is not installed.
    """
    try:
        from datasketch import MinHash
    except ImportError:
        logger.debug("datasketch not installed, MinHash unavailable")
        return None

    m = MinHash(num_perm=num_perm)
    text_lower = text.lower().strip()
    for i in range(max(1, len(text_lower) - 2)):
        gram = text_lower[i : i + 3]
        m.update(gram.encode("utf-8"))
    return m


def jaccard_similarity(sig_a, sig_b) -> float:
    """Compute approximate Jaccard similarity between two MinHash signatures.

    Returns 0.0 if either signature is None.
    """
    if sig_a is None or sig_b is None:
        return 0.0
    return float(sig_a.jaccard(sig_b))


def text_similarity(text_a: str, text_b: str, *, num_perm: int = NUM_PERM) -> float:
    """Convenience: compute Jaccard between two texts."""
    return jaccard_similarity(
        minhash_signature(text_a, num_perm=num_perm),
        minhash_signature(text_b, num_perm=num_perm),
    )
