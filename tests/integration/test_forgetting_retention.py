from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.memory.consolidation import ConsolidationEngine
from core.time_utils import now_jst


class _FakeVectorStore:
    def __init__(self, source_file: str) -> None:
        self.source_file = source_file
        self.deleted: list[tuple[str, list[str]]] = []

    def get_by_metadata(self, collection: str, where: dict, limit: int = 20) -> list[SimpleNamespace]:
        if where == {}:
            return []
        if where == {"source_file": self.source_file}:
            return [SimpleNamespace(document=SimpleNamespace(id="kotoha/episodes/old#0"))]
        return []

    def delete_documents(self, collection: str, ids: list[str]) -> bool:
        self.deleted.append((collection, ids))
        return True


@pytest.mark.asyncio
async def test_monthly_forget_archives_retention_expired_episodes(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "kotoha"
    episodes_dir = anima_dir / "episodes"
    knowledge_dir = anima_dir / "knowledge"
    episodes_dir.mkdir(parents=True)
    knowledge_dir.mkdir()

    old_date = (now_jst().date() - timedelta(days=45)).isoformat()
    recent_date = (now_jst().date() - timedelta(days=5)).isoformat()
    old_file = episodes_dir / f"{old_date}.md"
    recent_file = episodes_dir / f"{recent_date}.md"
    old_file.write_text("# Old\n\nArchive by retention.", encoding="utf-8")
    recent_file.write_text("# Recent\n\nKeep by retention.", encoding="utf-8")

    fake_store = _FakeVectorStore(f"episodes/{old_date}.md")
    config = SimpleNamespace(consolidation=SimpleNamespace(episode_retention_days=30))
    engine = ConsolidationEngine(anima_dir, "kotoha")

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.forgetting.ForgettingEngine._get_vector_store", return_value=fake_store),
        patch.object(engine, "_rebuild_rag_index"),
    ):
        result = await engine.monthly_forget()

    assert result["episode_retention"]["archived_count"] == 1
    assert result["episode_retention"]["deleted_indexed_chunks"] == 1
    assert f"episodes/{old_date}.md" in result["archived_files"]
    assert not old_file.exists()
    assert recent_file.exists()
    assert (anima_dir / "archive" / "episodes" / f"{old_date}.md").exists()
    assert fake_store.deleted == [
        ("kotoha_episodes", ["kotoha/episodes/old#0"]),
    ]
