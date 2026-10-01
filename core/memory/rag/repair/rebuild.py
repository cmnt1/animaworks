from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Source snapshots, staging rebuild, and metadata publication for RAG repair.

Snapshots are used only for explicit full rebuilds; they are not a writer lock.
The caller must still quiesce writers for a strictly current promotion.
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.i18n import t
from core.memory.io import atomic_write_text
from core.platform.atomic_io import atomic_write_json

logger = logging.getLogger("animaworks.rag.repair")


class RebuildVerificationError(RuntimeError):
    """Raised when a just-rebuilt vector DB is still missing its data.

    A rebuild that reports indexed chunks but whose collections are absent left
    a schema-less stub (e.g. upserts silently failed during concurrent work).
    Treating this as a failure lets the caller mark the repair failed so the
    cooldown engages instead of reporting a false success that immediately
    re-triggers another repair.
    """


def _reindex_into_store(
    vector_store,
    anima_name: str,
    *,
    include_shared: bool,
    anima_dir: Path | None = None,
    rebuild_bm25: bool = True,
    source_data_dir: Path | None = None,
    source_file_stats: dict | None = None,
) -> tuple[int, dict[str, str]]:
    """Index an anima's memory (and optionally shared collections) into a store."""
    from core.memory.rag import MemoryIndexer
    from core.memory.retrieval.bm25 import rebuild_longterm_bm25_index
    from core.org.company_resources import get_company_resources
    from core.paths import get_animas_dir, get_common_knowledge_dir, get_common_skills_dir, get_data_dir

    anima_dir = Path(anima_dir) if anima_dir is not None else get_animas_dir() / anima_name
    total_chunks = 0
    shared_hashes: dict[str, str] = {}
    source_options = (
        {"source_data_dir": source_data_dir, "source_file_stats": source_file_stats}
        if source_data_dir is not None
        else {}
    )
    indexer = MemoryIndexer(vector_store, anima_name, anima_dir, **source_options)
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

    from core.memory.facts.entity_index import load_entity_registry, rebuild_entity_collection

    # Resolve one registry snapshot for both the write and its expected count.
    # Each entry creates one entity document. Omitting these documents from the
    # count made otherwise successful full repairs fail verification.
    registry = load_entity_registry(anima_dir)
    entity_count = len(registry.get("entities", {}))
    if entity_count:
        if not rebuild_entity_collection(anima_dir, registry=registry, vector_store=vector_store):
            raise RebuildVerificationError(f"failed to fully rebuild entities for {anima_name}")
        total_chunks += entity_count

    if rebuild_bm25:
        bm25_result = rebuild_longterm_bm25_index(anima_dir)
        logger.info("Rebuilt long-term BM25 index for %s: documents=%d", anima_name, bm25_result.documents)

    if include_shared:
        base_dir = source_data_dir if source_data_dir is not None else get_data_dir()
        shared_indexer = MemoryIndexer(
            vector_store,
            anima_name="shared",
            anima_dir=base_dir,
            collection_prefix="shared",
            **source_options,
        )
        shared_sources = [
            (
                "common_knowledge",
                base_dir / "common_knowledge" if source_data_dir else get_common_knowledge_dir(),
                "*.md",
                "shared_common_knowledge_hash",
            ),
            (
                "common_skills",
                base_dir / "common_skills" if source_data_dir else get_common_skills_dir(),
                "SKILL.md",
                "shared_common_skills_hash",
            ),
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
            from core.memory.retrieval.rag_search import _compute_dir_hash

            shared_hashes[meta_key] = _compute_dir_hash(src_dir, glob)
    return total_chunks, shared_hashes


def build_staging_vectordb(
    anima_name: str,
    *,
    include_shared: bool,
    anima_dir: Path,
    staging: Path,
) -> tuple[int, dict[str, str]]:
    """Build from private inputs without publishing live DB or metadata."""
    import gc

    from core.memory.rag.direct_access import OWNER_CAPABILITY
    from core.memory.rag.store import create_chroma_vector_store

    anima_dir = anima_dir.resolve()
    staging = staging.resolve()
    if staging.parent != anima_dir or not staging.name.startswith("vectordb.staging-"):
        raise ValueError(f"direct Chroma rebuild path must be an anima staging directory: {staging}")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with snapshot_inputs(anima_dir, include_shared=include_shared) as inputs:
            store = create_chroma_vector_store(
                persist_dir=staging,
                anima_name=anima_name,
                allow_direct=OWNER_CAPABILITY,
            )
            try:
                chunks, shared_hashes = _reindex_into_store(
                    store,
                    anima_name,
                    include_shared=include_shared,
                    anima_dir=inputs.anima_dir,
                    rebuild_bm25=False,
                    source_data_dir=inputs.data_dir,
                    source_file_stats=inputs.file_stats,
                )
                store.verify_rebuilt_data(expected_chunks=chunks)
                save_rebuild_artifacts(staging, inputs)
                validate_rebuild_sources(staging, anima_dir)
                return chunks, shared_hashes
            finally:
                store.close()
                gc.collect()
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _repair_metadata_paths(anima_dir: Path) -> tuple[Path, ...]:
    from core.memory.rag.shared_meta import shared_index_meta_path
    from core.memory.retrieval.bm25 import longterm_bm25_delta_path, longterm_bm25_dirty_path, longterm_bm25_index_path

    return (
        anima_dir / "index_meta.json",
        shared_index_meta_path(anima_dir),
        longterm_bm25_index_path(anima_dir),
        longterm_bm25_dirty_path(anima_dir),
        longterm_bm25_delta_path(anima_dir),
    )


def _backup_repair_metadata(anima_dir: Path) -> tuple[Path, set[str]]:
    state_dir = anima_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(tempfile.mkdtemp(prefix=".rag-repair-metadata-", dir=state_dir))
    existing: set[str] = set()
    for path in _repair_metadata_paths(anima_dir):
        if path.is_file():
            relative = path.relative_to(anima_dir)
            existing.add(str(relative))
            (backup_dir / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_dir / relative)
    return backup_dir, existing


def _restore_repair_metadata(anima_dir: Path, backup_dir: Path, existing: set[str]) -> None:
    for path in _repair_metadata_paths(anima_dir):
        relative = path.relative_to(anima_dir)
        backup = backup_dir / relative
        if str(relative) in existing:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, path)
        elif path.exists():
            path.unlink()


ARTIFACT_DIR = ".rebuild"


@dataclass
class RebuildInputs:
    data_dir: Path
    anima_dir: Path
    manifest: dict
    file_stats: dict[str, os.stat_result]


def _source_files(root: Path) -> list[Path]:
    if root.is_symlink():
        raise ValueError(t("rag.rebuild_symlink_input", path=root))
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(t("rag.rebuild_symlink_input", path=path))
        if path.is_file():
            files.append(path)
    return files


def _fingerprint(root: Path) -> dict:
    files = {}
    for path in _source_files(root):
        before = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        after = path.stat()
        if (before.st_mtime_ns, before.st_size, before.st_ctime_ns) != (
            after.st_mtime_ns,
            after.st_size,
            after.st_ctime_ns,
        ):
            raise RuntimeError(t("rag.rebuild_input_changed"))
        key = "." if path == root else path.relative_to(root).as_posix()
        files[key] = {"sha256": digest, "mtime_ns": after.st_mtime_ns, "size": after.st_size}
    return {"exists": root.exists(), "files": files}


@contextmanager
def snapshot_inputs(anima_dir: Path, *, include_shared: bool) -> Iterator[RebuildInputs]:
    from core.org.company_resources import get_company_resources
    from core.paths import get_common_knowledge_dir, get_common_skills_dir, get_data_dir

    base = get_data_dir()
    name = anima_dir.name
    relative_anima = Path("animas") / name
    sources = [
        (anima_dir / scope, relative_anima / scope)
        for scope in ("knowledge", "episodes", "procedures", "skills", "facts")
    ]
    sources.extend(
        (anima_dir / path, relative_anima / path)
        for path in (
            "status.json",
            "state/conversation.json",
            "state/entity_registry.json",
            "state/skill_curator.jsonl",
        )
    )
    sources.extend((base / path, Path(path)) for path in (".ragignore", "config.json"))
    if include_shared:
        sources.extend(
            ((get_common_knowledge_dir(), Path("common_knowledge")), (get_common_skills_dir(), Path("common_skills")))
        )
        company = get_company_resources(anima_dir, data_dir=base)
        if company is not None:
            for scope, source in (("knowledge", company.knowledge_dir), ("skills", company.skills_dir)):
                sources.append((source, Path("companies") / company.name / scope))

    # Copy only source inputs, never live vectordb, index_meta or automatic
    # upsert quarantine state. Metadata/registry repair writes stay private.
    with tempfile.TemporaryDirectory(prefix=".rag-rebuild-inputs-", dir=anima_dir) as temporary:
        snapshot = Path(temporary)
        fingerprints = {str(source): _fingerprint(source) for source, _dest in sources}
        stats = {}
        for source, destination in sources:
            for path in _source_files(source):
                target = snapshot / destination
                if path != source:
                    target = target / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                original_stat = path.stat()
                shutil.copy2(path, target)
                stats[str(target)] = original_stat
            if source.is_dir():
                (snapshot / destination).mkdir(parents=True, exist_ok=True)
            if _fingerprint(snapshot / destination) != fingerprints[str(source)]:
                raise RuntimeError(t("rag.rebuild_input_changed"))
        if any(_fingerprint(source) != fingerprints[str(source)] for source, _dest in sources):
            raise RuntimeError(t("rag.rebuild_input_changed"))
        snapshot_anima = snapshot / relative_anima
        snapshot_anima.mkdir(parents=True, exist_ok=True)
        yield RebuildInputs(
            snapshot, snapshot_anima, {"owner": str(anima_dir.resolve()), "sources": fingerprints}, stats
        )


def save_rebuild_artifacts(staging: Path, inputs: RebuildInputs) -> None:
    target = staging / ARTIFACT_DIR
    target.mkdir()
    metadata = inputs.anima_dir / "index_meta.json"
    # Empty personal input can legitimately produce no index_meta file.
    contents = metadata.read_text(encoding="utf-8") if metadata.exists() else "{}"
    value = json.loads(contents)
    if not isinstance(value, dict):
        raise ValueError(t("rag.rebuild_invalid_metadata"))
    atomic_write_text(target / "index_meta.json", contents)
    atomic_write_text(target / "sources.json", json.dumps(inputs.manifest))


def validate_rebuild_sources(staging: Path, anima_dir: Path) -> None:
    manifest = json.loads((staging / ARTIFACT_DIR / "sources.json").read_text(encoding="utf-8"))
    if manifest.get("owner") != str(anima_dir.resolve()) or not isinstance(manifest.get("sources"), dict):
        raise ValueError(t("rag.rebuild_invalid_manifest"))
    for source, expected in manifest["sources"].items():
        if _fingerprint(Path(source)) != expected:
            raise RuntimeError(t("rag.rebuild_input_changed"))


def publish_rebuild_metadata(anima_dir: Path) -> None:
    path = anima_dir / "vectordb" / ARTIFACT_DIR / "index_meta.json"
    content = path.read_text(encoding="utf-8")
    if not isinstance(json.loads(content), dict):
        raise ValueError(t("rag.rebuild_invalid_metadata"))
    atomic_write_text(anima_dir / "index_meta.json", content)


def _main() -> int:
    parser = argparse.ArgumentParser(description="Build a phase3 RAG repair staging database")
    parser.add_argument("--build-staging", action="store_true", required=True)
    parser.add_argument("--anima", required=True)
    parser.add_argument("--anima-dir", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--shared", action="store_true")
    args = parser.parse_args()
    chunks, shared_hashes = build_staging_vectordb(
        args.anima,
        include_shared=args.shared,
        anima_dir=args.anima_dir,
        staging=args.staging,
    )
    atomic_write_json(
        args.result,
        {"chunks": chunks, "shared_hashes": shared_hashes},
        indent=None,
        trailing_newline=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
