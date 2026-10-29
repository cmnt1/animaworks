"""Unit tests for CLI index --shared flag."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cli.commands.index_cmd import (
    _check_model_change,
    _is_anima_enabled,
    _save_global_index_meta,
    index_command,
    setup_index_command,
)
from core.memory.rag.indexer import IndexDirectoryResult


@pytest.fixture(autouse=True)
def _runtime_data_dir(data_dir_at_tmp_path: Path) -> None:
    """Use real runtime path accessors for each test's temporary root."""


# ── _is_anima_enabled ─────────────────────────────────────


class TestIsAnimaEnabled:
    def test_enabled_when_no_status_file(self, tmp_path: Path) -> None:
        assert _is_anima_enabled(tmp_path) is True

    def test_enabled_explicitly(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text('{"enabled": true}')
        assert _is_anima_enabled(tmp_path) is True

    def test_disabled(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text('{"enabled": false}')
        assert _is_anima_enabled(tmp_path) is False

    def test_enabled_default_when_key_missing(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text('{"model": "claude-sonnet-4-6"}')
        assert _is_anima_enabled(tmp_path) is True

    def test_corrupted_json_treated_as_enabled(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text("{bad")
        assert _is_anima_enabled(tmp_path) is True


class TestGlobalIndexMeta:
    def test_save_global_index_meta_records_e5_prefix(self, tmp_path: Path) -> None:
        with patch("core.memory.rag.embedding.get_embedding_e5_prefix_enabled", return_value=True):
            _save_global_index_meta(tmp_path, "test-embedding-model")

        data = json.loads((tmp_path / "index_meta.json").read_text(encoding="utf-8"))
        assert data["embedding_model"] == "test-embedding-model"
        assert data["embedding_e5_prefix"] is True

    def test_check_model_change_rejects_e5_prefix_mismatch_without_full(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "index_meta.json").write_text(
            json.dumps({"embedding_model": "test-embedding-model", "embedding_e5_prefix": False}),
            encoding="utf-8",
        )

        with (
            patch("core.memory.rag.embedding.get_embedding_model_name", return_value="test-embedding-model"),
            patch("core.memory.rag.embedding.get_embedding_e5_prefix_enabled", return_value=True),
            pytest.raises(SystemExit),
        ):
            _check_model_change(tmp_path, full=False)


# ── setup_index_command (--shared flag registration) ──────


class TestSetupSharedFlag:
    def test_shared_flag_registered(self) -> None:
        """--shared flag is available in the argument parser."""
        parser = argparse.ArgumentParser()
        subs = parser.add_subparsers()
        setup_index_command(subs)
        args = parser.parse_args(["index", "--shared"])
        assert args.shared is True

    def test_shared_defaults_false(self) -> None:
        parser = argparse.ArgumentParser()
        subs = parser.add_subparsers()
        setup_index_command(subs)
        args = parser.parse_args(["index"])
        assert args.shared is False


@pytest.fixture(autouse=True)
def _temporary_vector_access(monkeypatch):
    @contextmanager
    def open_access(*_args, **_kwargs):
        store = MagicMock()
        store.delete_collection.return_value = True
        yield SimpleNamespace(
            mode="owner",
            store=store,
            repair=MagicMock(return_value={"ok": True, "status": "success"}),
        )

    monkeypatch.setattr("core.memory.rag.cli_access.open_vector_access", open_access)


def test_index_command_opens_each_anima_once_for_personal_and_shared_indexing(tmp_path: Path) -> None:
    from contextlib import contextmanager

    anima_dir = tmp_path / "animas" / "alice"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "knowledge" / "note.md").write_text("# Personal", encoding="utf-8")
    common_dir = tmp_path / "common_knowledge"
    common_dir.mkdir()
    (common_dir / "reference.md").write_text("# Shared", encoding="utf-8")
    args = argparse.Namespace(anima=None, full=False, shared=False, dry_run=False)
    access = SimpleNamespace(store=MagicMock())
    indexer = MagicMock()
    indexer.index_directory.return_value = IndexDirectoryResult(chunks_indexed=1, files_indexed=1)

    @contextmanager
    def open_access(*_args, **_kwargs):
        yield access

    with (
        patch("cli.commands.index_cmd._check_model_change", return_value="test-model"),
        patch("core.memory.rag.MemoryIndexer", return_value=indexer),
        patch("core.memory.facts.entity_index.rebuild_entity_collection", return_value=True),
        patch("core.memory.retrieval.bm25.rebuild_longterm_bm25_index", return_value=MagicMock(documents=1)),
        patch("core.memory.rag.cli_access.open_vector_access", side_effect=open_access) as open_vector,
        patch("core.config.models.read_anima_company_checked", return_value=(True, None)),
        patch("core.org.company_resources.get_company_resources_for_company", return_value=None),
        patch("core.memory.rag.shared_meta.reset_shared_for_company_change", return_value=True),
        patch("core.memory.rag.shared_meta.read_shared_hash", return_value=""),
        patch("core.memory.rag.shared_meta.write_shared_hash"),
    ):
        index_command(args)

    open_vector.assert_called_once_with("alice", anima_dir, purpose="index")
    assert indexer.index_directory.call_count == 2


def test_index_command_does_not_index_shared_user_store(tmp_path: Path) -> None:
    (tmp_path / "animas" / "alice").mkdir(parents=True)
    (tmp_path / "shared" / "users" / "user-1").mkdir(parents=True)
    args = argparse.Namespace(anima=None, full=False, shared=False, dry_run=True)
    shared_store = MagicMock()

    with (
        patch("cli.commands.index_cmd._check_model_change", return_value="test-model"),
        patch("cli.commands.index_cmd._index_anima", return_value=0),
        patch("cli.commands.index_cmd._setup_server_delegation", return_value=True) as delegation,
        patch("core.memory.rag.vector_registry.get_vector_store", return_value=shared_store) as get_store,
    ):
        index_command(args)

    delegation.assert_not_called()
    get_store.assert_not_called()


def test_index_command_skips_repair_locked_anima(tmp_path: Path, data_dir: Path) -> None:
    """CLI indexing must not open a local vector store while repair lock is held."""
    animas_dir = tmp_path / "animas"
    anima_dir = animas_dir / "alice"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "knowledge" / "note.md").write_text("# Note", encoding="utf-8")

    args = argparse.Namespace(anima="alice", full=False, shared=False, dry_run=False)

    with (
        patch("cli.commands.index_cmd._setup_server_delegation", return_value=False),
        patch("cli.commands.index_cmd._check_model_change", return_value="test-model"),
        patch("core.memory.rag.repair.is_repair_locked", return_value=True),
        patch("core.memory.rag.vector_registry.get_vector_store") as mock_get_vs,
        patch("core.memory.rag.MemoryIndexer") as mock_indexer,
    ):
        index_command(args)

    mock_get_vs.assert_not_called()
    mock_indexer.assert_not_called()


def test_index_command_indexes_phase3_anima_through_access(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "knowledge" / "note.md").write_text("# Note", encoding="utf-8")
    (anima_dir / "status.json").write_text('{"process_model":"phase3"}', encoding="utf-8")
    args = argparse.Namespace(anima="alice", full=False, shared=False, dry_run=False)
    mock_indexer = MagicMock()
    mock_indexer.index_directory.return_value = IndexDirectoryResult(chunks_indexed=2, files_indexed=1)

    with (
        patch("cli.commands.index_cmd._check_model_change", return_value="test-model"),
        patch("core.memory.rag.MemoryIndexer", return_value=mock_indexer),
        patch("core.memory.facts.entity_index.rebuild_entity_collection", return_value=True),
        patch("core.memory.retrieval.bm25.rebuild_longterm_bm25_index", return_value=MagicMock(documents=1)),
        patch("core.memory.rag.cli_access.open_vector_access") as open_access,
    ):
        from contextlib import nullcontext

        access = SimpleNamespace(mode="owner", store=MagicMock(), repair=MagicMock())
        open_access.return_value = nullcontext(access)
        index_command(args)

    open_access.assert_called_once_with("alice", anima_dir, purpose="index")
    mock_indexer.index_directory.assert_called_once_with(anima_dir / "knowledge", "knowledge", force=False)


def test_index_command_rebuilds_longterm_bm25(tmp_path: Path) -> None:
    """CLI indexing rebuilds the persisted long-term BM25 index."""
    animas_dir = tmp_path / "animas"
    anima_dir = animas_dir / "alice"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "knowledge" / "note.md").write_text("# Note", encoding="utf-8")

    args = argparse.Namespace(anima="alice", full=False, shared=False, dry_run=False)
    mock_store = MagicMock()

    with (
        patch("cli.commands.index_cmd._setup_server_delegation", return_value=False),
        patch("cli.commands.index_cmd._check_model_change", return_value="test-model"),
        patch("core.memory.rag.repair.is_repair_locked", return_value=False),
        patch("core.memory.rag.vector_registry.get_vector_store", return_value=mock_store),
        patch("core.memory.rag.MemoryIndexer") as mock_indexer_cls,
        patch("core.memory.retrieval.bm25.rebuild_longterm_bm25_index") as mock_rebuild,
    ):
        mock_indexer = MagicMock()
        mock_indexer.index_directory.return_value = IndexDirectoryResult(chunks_indexed=1, files_indexed=1)
        mock_indexer_cls.return_value = mock_indexer
        mock_rebuild.return_value = MagicMock(documents=1)

        index_command(args)

    mock_rebuild.assert_called_once_with(anima_dir)


def test_index_command_full_reindexes_facts(tmp_path: Path) -> None:
    """CLI full rebuild sends facts JSONL through the MemoryIndexer chunker."""
    anima_dir = tmp_path / "animas" / "alice"
    (anima_dir / "facts").mkdir(parents=True)
    (anima_dir / "facts" / "2026-07-15.jsonl").write_text('{"text":"fact"}\n', encoding="utf-8")
    args = argparse.Namespace(anima="alice", full=True, shared=False, dry_run=False)
    mock_store = MagicMock()

    with (
        patch("cli.commands.index_cmd._setup_server_delegation", return_value=False),
        patch("cli.commands.index_cmd._check_model_change", return_value="test-model"),
        patch("core.memory.rag.repair.is_repair_locked", return_value=False),
        patch("core.memory.rag.vector_registry.get_vector_store", return_value=mock_store),
        patch("core.memory.rag.MemoryIndexer") as mock_indexer_cls,
        patch("core.memory.retrieval.bm25.rebuild_longterm_bm25_index") as mock_rebuild,
    ):
        mock_indexer = MagicMock()
        mock_indexer.index_directory.return_value = IndexDirectoryResult(chunks_indexed=1, files_indexed=1)
        mock_indexer_cls.return_value = mock_indexer
        mock_rebuild.return_value = MagicMock(documents=0)
        index_command(args)

    mock_indexer.index_directory.assert_called_once_with(
        anima_dir / "facts",
        "facts",
        force=True,
    )


def test_index_command_full_uses_atomic_repair_before_indexing(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "knowledge" / "note.md").write_text("# Note", encoding="utf-8")
    args = argparse.Namespace(anima="alice", full=True, shared=False, dry_run=False)
    mock_store = MagicMock()
    access = SimpleNamespace(
        mode="owner",
        store=mock_store,
        repair=MagicMock(return_value={"ok": True, "status": "success"}),
    )
    access_context = MagicMock()
    access_context.__enter__.return_value = access

    with (
        patch("cli.commands.index_cmd._setup_server_delegation", return_value=False),
        patch("cli.commands.index_cmd._check_model_change", return_value="test-model"),
        patch("core.memory.rag.repair.is_repair_locked", return_value=False),
        patch("core.memory.rag.vector_registry.get_vector_store", return_value=mock_store),
        patch("core.memory.rag.MemoryIndexer") as mock_indexer_cls,
        patch("core.memory.rag.cli_access.open_vector_access", return_value=access_context),
    ):
        index_command(args)

    access.repair.assert_called_once_with(include_shared=True)
    mock_indexer_cls.assert_called_once()
