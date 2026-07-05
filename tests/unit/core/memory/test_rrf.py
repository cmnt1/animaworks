"""Unit tests for core/memory/retrieval/rrf.py dedup keying and merge."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.memory.retrieval.rrf import legacy_result_key, rrf_merge


def test_legacy_result_key_uses_identity_fields_when_present() -> None:
    item = {"source_file": "knowledge/a.md", "chunk_index": 2, "ts": "t", "memory_type": "knowledge"}

    assert legacy_result_key(item) == "knowledge/a.md\x002\x00t\x00knowledge"


def test_legacy_result_key_distinguishes_empty_field_items_by_content() -> None:
    # Graph/synthetic rows can arrive with all identity fields empty/0. Without
    # a content fallback they would collapse onto one dedup key (F20).
    a = {"source_file": "", "chunk_index": 0, "ts": "", "memory_type": "", "content": "first row"}
    b = {"source_file": "", "chunk_index": 0, "ts": "", "memory_type": "", "content": "second row"}

    key_a = legacy_result_key(a)
    key_b = legacy_result_key(b)

    assert key_a != key_b
    # Same content still maps to the same key (real duplicates still dedup).
    assert legacy_result_key(dict(a)) == key_a


def test_rrf_merge_keeps_both_empty_field_items() -> None:
    a = {"content": "alpha payload"}
    b = {"content": "beta payload"}

    merged = rrf_merge([[a, b]], key_fn=legacy_result_key, top_k=10)

    contents = {row["content"] for row in merged}
    assert contents == {"alpha payload", "beta payload"}


def test_rrf_merge_empty_content_items_fall_back_to_identity_key() -> None:
    # Fully empty rows (no content either) share the identity key and dedup as
    # before — no crash, no key explosion.
    a = {"source_file": "", "chunk_index": 0, "ts": "", "memory_type": "", "content": ""}
    b = {"source_file": "", "chunk_index": 0, "ts": "", "memory_type": "", "content": ""}

    merged = rrf_merge([[a, b]], key_fn=legacy_result_key, top_k=10)

    assert len(merged) == 1
