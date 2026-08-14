from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.bm25 import rebuild_longterm_bm25_index, search_longterm_memory_bm25


@pytest.mark.e2e
def test_priming_bm25_skip_contract_uses_index_without_source_scan(tmp_path: Path) -> None:
    """F priming can skip source validation while normal search still reconciles files."""
    anima_dir = tmp_path / "animas" / "mei"
    source = anima_dir / "episodes" / "recall.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Recall\n\nZephyrNova launch review completed.", encoding="utf-8")
    rebuild_longterm_bm25_index(anima_dir)
    source.unlink()

    priming_hits = search_longterm_memory_bm25(
        anima_dir,
        "ZephyrNova",
        memory_types=("episodes",),
        validate_sources=False,
    )
    validated_hits = search_longterm_memory_bm25(
        anima_dir,
        "ZephyrNova",
        memory_types=("episodes",),
        validate_sources=True,
    )

    assert [hit["source_file"] for hit in priming_hits] == ["episodes/recall.md"]
    assert validated_hits == []
