from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Quarantine and reindex helpers for RAG auto-repair."""

import logging
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("animaworks.rag.repair")


def _has_active_repair_fence(anima_name: str, *, anima_dir: Path | None = None) -> bool:
    from core.memory.rag import repair_state

    animas_dir = anima_dir.parent if anima_dir is not None else None
    state = repair_state.read_state(anima_name, animas_dir=animas_dir)
    return state.get("status") in repair_state.ACTIVE_REPAIR_STATUSES


def reset_worker_vector_store(anima_name: str) -> bool:
    """Reset the vector worker's cached store for an anima when configured."""
    if not os.environ.get("ANIMAWORKS_VECTOR_URL"):
        return False
    try:
        from core.memory.rag.http_store import HttpVectorStore
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(anima_name)
        if isinstance(store, HttpVectorStore):
            return store.reset_store()
    except Exception:
        logger.debug("Failed to reset vector worker store for %s", anima_name, exc_info=True)
    return False


def verify_worker_vector_store(anima_name: str, *, expected_chunks: int) -> bool:
    """Verify the swapped DB through the fenced worker using the repair nonce."""
    repair_nonce = os.environ.get("ANIMAWORKS_RAG_REPAIR_NONCE")
    if not repair_nonce:
        return False
    try:
        from core.memory.rag.http_store import HttpVectorStore
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(anima_name)
        if isinstance(store, HttpVectorStore):
            return store.verify_repair(repair_nonce, expected_chunks=expected_chunks)
    except Exception:
        logger.debug("Failed to verify rebuilt vector store for %s", anima_name, exc_info=True)
    return False


def quarantine_vectordb(anima_name: str) -> Path | None:
    import gc

    from core.memory.rag.singleton import reset_vector_store
    from core.paths import get_anima_vectordb_dir

    reset_worker_vector_store(anima_name)
    reset_vector_store(anima_name)
    gc.collect()

    source = get_anima_vectordb_dir(anima_name)
    if not source.exists():
        return None

    archive_dir = source.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dest = archive_dir / f"vectordb-corrupt-{stamp}"
    suffix = 1
    while dest.exists():
        suffix += 1
        dest = archive_dir / f"vectordb-corrupt-{stamp}-{suffix}"
    shutil.move(str(source), str(dest))

    # Recreate an empty vectordb dir and drop any worker handle that a concurrent
    # read may have pinned during the move. The pre-move reset above only releases
    # handles so the OS move succeeds; it does not stop a priming read arriving
    # mid-move from lazily re-creating the worker's cached store against the
    # now-missing path. Such a store opens a schema-less stub ("no such table:
    # collections") that the upcoming reindex would reuse, writing an empty DB and
    # leaving reads broken indefinitely. Resetting here forces the reindex to
    # rebuild a clean store bound to the recreated directory.
    source.mkdir(parents=True, exist_ok=True)
    reset_worker_vector_store(anima_name)
    reset_vector_store(anima_name)
    return dest


class RebuildVerificationError(RuntimeError):
    """Raised when a just-rebuilt vector DB is still missing its data.

    A rebuild that reports indexed chunks but whose collections are absent left
    a schema-less stub (e.g. upserts silently failed under worker contention).
    Treating this as a failure lets the caller mark the repair failed so the
    cooldown engages instead of reporting a false success that immediately
    re-triggers another repair.
    """


def verify_rebuilt_vectordb(anima_name: str, *, expected_chunks: int) -> None:
    """Confirm a freshly rebuilt vector DB actually holds its collections.

    Raises ``RebuildVerificationError`` when ``expected_chunks`` is positive but
    the store has no collections (or cannot be listed) — the signature of a stub
    left behind by failed upserts. A genuinely empty anima (``expected_chunks``
    == 0) is considered healthy.
    """
    if expected_chunks <= 0:
        return
    from core.memory.rag.singleton import get_vector_store

    store = get_vector_store(anima_name)
    if store is None:
        raise RebuildVerificationError(
            f"vector store unavailable for {anima_name} after rebuild (indexed {expected_chunks} chunks)"
        )
    collections = store.list_collections_checked()
    if collections is None:
        raise RebuildVerificationError(
            f"rebuilt vector DB for {anima_name} is unreadable (indexed {expected_chunks} chunks)"
        )
    if not collections:
        raise RebuildVerificationError(
            f"rebuilt vector DB for {anima_name} has no collections despite indexing {expected_chunks} chunks "
            "(stub left by failed upserts)"
        )


def _reindex_into_store(
    vector_store,
    anima_name: str,
    *,
    include_shared: bool,
    anima_dir: Path | None = None,
) -> tuple[int, dict[str, str]]:
    """Index an anima's memory (and optionally shared collections) into a store."""
    from core.company_resources import get_company_resources
    from core.memory.bm25 import rebuild_longterm_bm25_index
    from core.memory.rag import MemoryIndexer
    from core.paths import get_animas_dir, get_common_knowledge_dir, get_common_skills_dir, get_data_dir

    anima_dir = Path(anima_dir) if anima_dir is not None else get_animas_dir() / anima_name
    total_chunks = 0
    shared_hashes: dict[str, str] = {}
    indexer = MemoryIndexer(vector_store, anima_name, anima_dir)
    for memory_type in ("knowledge", "episodes", "procedures", "skills", "facts"):
        memory_dir = anima_dir / memory_type
        if memory_dir.is_dir():
            result = indexer.index_directory(memory_dir, memory_type, force=True)
            if result.files_failed or result.files_unprocessed:
                raise RebuildVerificationError(
                    f"failed to fully rebuild {memory_type} for {anima_name}: "
                    f"failed={result.files_failed} unprocessed={result.files_unprocessed}"
                )
            total_chunks += result.chunks_indexed

    state_dir = anima_dir / "state"
    if (state_dir / "conversation.json").is_file():
        total_chunks += indexer.index_conversation_summary(state_dir, anima_name, force=True)

    bm25_result = rebuild_longterm_bm25_index(anima_dir)
    logger.info("Rebuilt long-term BM25 index for %s: documents=%d", anima_name, bm25_result.documents)

    if include_shared:
        base_dir = get_data_dir()
        shared_indexer = MemoryIndexer(
            vector_store,
            anima_name="shared",
            anima_dir=base_dir,
            collection_prefix="shared",
        )
        shared_sources = [
            ("common_knowledge", get_common_knowledge_dir(), "*.md", "shared_common_knowledge_hash"),
            ("common_skills", get_common_skills_dir(), "SKILL.md", "shared_common_skills_hash"),
        ]
        company_resources = get_company_resources(anima_dir, data_dir=base_dir)
        if company_resources is not None:
            shared_sources.extend(
                (
                    (
                        "common_knowledge",
                        company_resources.knowledge_dir,
                        "*.md",
                        "shared_company_knowledge_hash",
                    ),
                    (
                        "common_skills",
                        company_resources.skills_dir,
                        "SKILL.md",
                        "shared_company_skills_hash",
                    ),
                )
            )
        for label, src_dir, glob, meta_key in shared_sources:
            if not src_dir.is_dir():
                continue
            result = shared_indexer.index_directory(src_dir, label, force=True)
            if result.files_failed or result.files_unprocessed:
                raise RebuildVerificationError(
                    f"failed to fully rebuild {meta_key} for {anima_name}: "
                    f"failed={result.files_failed} unprocessed={result.files_unprocessed}"
                )
            total_chunks += result.chunks_indexed
            from core.memory.rag_search import _compute_dir_hash

            shared_hashes[meta_key] = _compute_dir_hash(src_dir, glob)
    return total_chunks, shared_hashes


def full_reindex(anima_name: str, *, include_shared: bool) -> int:
    """Reindex an anima in place via the vector worker (legacy path)."""
    from core.memory.rag.singleton import get_vector_store
    from core.paths import get_animas_dir

    if not os.environ.get("ANIMAWORKS_VECTOR_URL"):
        raise RuntimeError("RAG reindex requires ANIMAWORKS_VECTOR_URL; run it through the vector worker")
    vector_store = get_vector_store(anima_name)
    if vector_store is None:
        raise RuntimeError(f"Vector store unavailable for {anima_name}")
    chunks, shared_hashes = _reindex_into_store(vector_store, anima_name, include_shared=include_shared)
    if shared_hashes:
        from core.memory.rag.shared_meta import write_shared_hashes

        write_shared_hashes(get_animas_dir() / anima_name, shared_hashes)
    return chunks


def _backup_bm25(anima_dir: Path) -> tuple[Path, set[str]]:
    from core.memory.bm25 import longterm_bm25_dirty_path, longterm_bm25_index_path

    state_dir = anima_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(tempfile.mkdtemp(prefix=".rag-repair-bm25-", dir=state_dir))
    existing: set[str] = set()
    for path in (longterm_bm25_index_path(anima_dir), longterm_bm25_dirty_path(anima_dir)):
        if path.is_file():
            existing.add(path.name)
            shutil.copy2(path, backup_dir / path.name)
    return backup_dir, existing


def _restore_bm25(anima_dir: Path, backup_dir: Path, existing: set[str]) -> None:
    from core.memory.bm25 import longterm_bm25_dirty_path, longterm_bm25_index_path

    for path in (longterm_bm25_index_path(anima_dir), longterm_bm25_dirty_path(anima_dir)):
        backup = backup_dir / path.name
        if path.name in existing:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, path)
        elif path.exists():
            path.unlink()


def atomic_rebuild_vectordb(
    anima_name: str,
    *,
    include_shared: bool,
    anima_dir: Path | None = None,
) -> tuple[int, Path | None]:
    """Build a fresh vector DB in a staging dir and atomically swap it in.

    Unlike the in-place rebuild (quarantine the live DB, then reindex into the
    now-empty live path), this keeps the live DB intact and queryable for the
    whole slow reindex and only swaps at the end. Benefits:

    - A failed rebuild leaves the live DB untouched (no data loss on failure).
    - The worker is reset only twice (at the swap) instead of for the whole
      rebuild, and never serves a half-built DB.
    - The build uses a process-local direct ChromaDB client whose system cache
      is isolated from the worker's, so it cannot be corrupted by — or corrupt —
      live worker traffic.

    Embeddings are still generated via the server (``ANIMAWORKS_EMBED_URL``);
    only the vector writes go to the local staging store. Returns
    ``(chunks_indexed, archive_path)``.
    """
    import gc

    from core.memory.rag.singleton import reset_vector_store
    from core.memory.rag.store import create_chroma_vector_store
    from core.paths import get_anima_vectordb_dir

    resolved_anima_dir = Path(anima_dir) if anima_dir is not None else get_anima_vectordb_dir(anima_name).parent
    live = resolved_anima_dir / "vectordb"
    staging = live.parent / f"vectordb.staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    bm25_backup, bm25_existing = _backup_bm25(resolved_anima_dir)
    archive: Path | None = None
    swap_started = False
    succeeded = False

    try:
        prev_allow = os.environ.get("ANIMAWORKS_ALLOW_DIRECT_CHROMA")
        os.environ["ANIMAWORKS_ALLOW_DIRECT_CHROMA"] = "1"
        try:
            store = create_chroma_vector_store(persist_dir=staging, anima_name=anima_name)
            try:
                chunks, shared_hashes = _reindex_into_store(
                    store,
                    anima_name,
                    include_shared=include_shared,
                    anima_dir=resolved_anima_dir,
                )
                if chunks > 0:
                    collections = store.list_collections_checked()
                    if collections is None:
                        raise RebuildVerificationError(
                            f"staged vector DB for {anima_name} is unreadable despite indexing {chunks} chunks"
                        )
                    if not collections:
                        raise RebuildVerificationError(
                            f"staged vector DB for {anima_name} has no collections despite indexing {chunks} chunks"
                        )
            finally:
                store.close()
                gc.collect()
        finally:
            if prev_allow is None:
                os.environ.pop("ANIMAWORKS_ALLOW_DIRECT_CHROMA", None)
            else:
                os.environ["ANIMAWORKS_ALLOW_DIRECT_CHROMA"] = prev_allow

        if not _has_active_repair_fence(anima_name, anima_dir=resolved_anima_dir):
            raise RebuildVerificationError(
                f"active RAG repair access fence missing for {anima_name}; refusing vector DB swap"
            )
        if not reset_worker_vector_store(anima_name):
            raise RebuildVerificationError(f"vector worker reset failed before swap for {anima_name}")
        reset_vector_store(anima_name)

        swap_started = True
        if live.exists():
            archive_dir = live.parent / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            archive = archive_dir / f"vectordb-corrupt-{stamp}"
            suffix = 1
            while archive.exists():
                suffix += 1
                archive = archive_dir / f"vectordb-corrupt-{stamp}-{suffix}"
            shutil.move(str(live), str(archive))
        shutil.move(str(staging), str(live))

        if not reset_worker_vector_store(anima_name):
            raise RebuildVerificationError(f"vector worker reset failed after swap for {anima_name}")
        reset_vector_store(anima_name)
        if not verify_worker_vector_store(anima_name, expected_chunks=chunks):
            raise RebuildVerificationError(f"vector worker verification failed after swap for {anima_name}")

        if shared_hashes:
            from core.memory.rag.shared_meta import write_shared_hashes

            write_shared_hashes(resolved_anima_dir, shared_hashes)
        from core.memory.rag.shared_check_registry import invalidate_shared_checks

        invalidate_shared_checks(anima_name)
        succeeded = True
        return chunks, archive
    except BaseException as exc:
        rollback_errors: list[str] = []
        if swap_started:
            try:
                reset_worker_vector_store(anima_name)
                reset_vector_store(anima_name)
                if live.exists():
                    failed_dir = live.parent / "archive"
                    failed_dir.mkdir(parents=True, exist_ok=True)
                    failed_stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                    failed_live = failed_dir / f"vectordb-rebuild-failed-{failed_stamp}"
                    suffix = 1
                    while failed_live.exists():
                        suffix += 1
                        failed_live = failed_dir / f"vectordb-rebuild-failed-{failed_stamp}-{suffix}"
                    shutil.move(str(live), str(failed_live))
                if archive is not None and archive.exists():
                    shutil.move(str(archive), str(live))
                reset_vector_store(anima_name)
                if not reset_worker_vector_store(anima_name):
                    rollback_errors.append("worker reset failed after rollback")
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        try:
            _restore_bm25(resolved_anima_dir, bm25_backup, bm25_existing)
        except Exception as rollback_exc:
            rollback_errors.append(f"BM25 rollback failed: {rollback_exc}")
        if rollback_errors:
            raise RebuildVerificationError(f"{exc}; rollback incomplete: {'; '.join(rollback_errors)}") from exc
        raise
    finally:
        if not succeeded:
            shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(bm25_backup, ignore_errors=True)
