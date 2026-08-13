from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import orjson
import pytest

from core.memory.bm25 import LONGTERM_BM25_SCHEMA_VERSION, longterm_bm25_index_path


@pytest.mark.performance
def test_longterm_bm25_cold_call_p95_under_one_second(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "search-perf"
    source = anima_dir / "knowledge" / "large.md"
    source.parent.mkdir(parents=True)
    source.write_text("performance corpus source", encoding="utf-8")
    stat = source.stat()
    documents = []
    filler = "x" * 256
    for index in range(20_000):
        tokens = ["baseline", "memory"]
        if index == 19_999:
            tokens.append("needle19999")
        documents.append(
            {
                "doc_id": f"search-perf/knowledge/large.md#{index}",
                "source_file": "knowledge/large.md",
                "content": f"{filler} {index}",
                "tokens": tokens,
                "token_counts": {token: 1 for token in tokens},
                "doc_len": len(tokens),
                "source_mtime_ns": stat.st_mtime_ns,
                "source_size": stat.st_size,
                "chunk_index": index,
                "total_chunks": 20_000,
                "memory_type": "knowledge",
                "metadata": {"source_file": "knowledge/large.md"},
            }
        )
    payload = {
        "schema_version": LONGTERM_BM25_SCHEMA_VERSION,
        "memory_types": ["knowledge"],
        "document_count": len(documents),
        "avgdl": 2.00005,
        "document_frequency": {"baseline": 20_000, "memory": 20_000, "needle19999": 1},
        "documents": documents,
    }
    index_path = longterm_bm25_index_path(anima_dir)
    index_path.parent.mkdir(parents=True)
    index_path.write_bytes(orjson.dumps(payload))
    script = (
        "from pathlib import Path; from time import perf_counter; "
        "from core.memory.bm25 import search_longterm_memory_bm25; "
        f"p=Path({str(anima_dir)!r}); t=perf_counter(); "
        "r=search_longterm_memory_bm25(p,'needle19999',memory_types=('knowledge',)); "
        "assert r and r[0]['chunk_index']==19999; print(perf_counter()-t)"
    )

    durations = [
        float(
            subprocess.run(
                [sys.executable, "-c", script],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        for _ in range(5)
    ]

    assert max(durations) < 1.0, json.dumps(durations)
