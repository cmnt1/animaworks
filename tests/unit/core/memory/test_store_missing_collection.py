# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for missing-collection query logging in ChromaVectorStore.

A collection that has never received data (e.g. ``{anima}_facts`` before any
fact was indexed) is hit by every retrieval.  It must return an empty result
with at most one loud log line per collection — not a WARNING flood into
errors.log (production hit ~27k such warnings before this guard).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tests.conftest import CHROMADB_AVAILABLE

pytestmark = pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="chromadb not installed")


@pytest.fixture
def store(tmp_path: Path):
    from core.memory.rag.store import ChromaVectorStore

    s = ChromaVectorStore(persist_dir=tmp_path / "vectordb", anima_name="testanima")
    yield s
    s.close()


class TestMissingCollectionQuery:
    def test_returns_empty_and_logs_info_once_then_debug(self, store, caplog: pytest.LogCaptureFixture) -> None:
        embedding = [0.0] * 8
        with caplog.at_level(logging.DEBUG, logger="animaworks.rag.store"):
            assert store.query("testanima_facts", embedding) == []
            assert store.query("testanima_facts", embedding) == []

        missing_logs = [r for r in caplog.records if "does not exist yet" in r.getMessage()]
        assert [r.levelno for r in missing_logs] == [logging.INFO, logging.DEBUG]

        warning_logs = [r for r in caplog.records if "ChromaDB query failed" in r.getMessage()]
        assert warning_logs == []

    def test_each_collection_gets_its_own_first_log(self, store, caplog: pytest.LogCaptureFixture) -> None:
        embedding = [0.0] * 8
        with caplog.at_level(logging.DEBUG, logger="animaworks.rag.store"):
            store.query("testanima_facts", embedding)
            store.query("testanima_knowledge", embedding)

        infos = [r for r in caplog.records if "does not exist yet" in r.getMessage() and r.levelno == logging.INFO]
        assert len(infos) == 2

    def test_existing_collection_still_queries_normally(self, store, caplog: pytest.LogCaptureFixture) -> None:
        store.create_collection("testanima_episodes")
        with caplog.at_level(logging.DEBUG, logger="animaworks.rag.store"):
            result = store.query("testanima_episodes", [0.0] * 8)
        assert result == []
        assert not any("does not exist yet" in r.getMessage() for r in caplog.records)


class TestIsMissingCollectionError:
    def test_matches_chroma_wordings(self) -> None:
        from core.memory.rag.store import _is_missing_collection_error

        assert _is_missing_collection_error(ValueError("Collection [sakura_facts] does not exist"))
        assert _is_missing_collection_error(ValueError("Collection sakura_facts not found"))
        assert not _is_missing_collection_error(ValueError("database disk image is malformed"))
        assert not _is_missing_collection_error(ValueError("no such table: collections"))
