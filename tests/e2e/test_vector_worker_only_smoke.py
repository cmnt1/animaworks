from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tests.conftest import CHROMADB_AVAILABLE


@pytest.mark.e2e
def test_temporary_vector_worker_rejects_per_anima_operations_in_phase3(data_dir: Path) -> None:
    """The phase3-fixed worker refuses per-anima native ownership, even for legacy status data."""
    if not CHROMADB_AVAILABLE:
        pytest.skip("ChromaDB is not installed")

    from core.memory.rag.vector_worker_client import start_temporary_vector_worker

    anima_dir = data_dir / "animas" / "worker_smoke"
    anima_dir.mkdir(parents=True, exist_ok=True)
    (anima_dir / "status.json").write_text('{"process_model": "legacy"}', encoding="utf-8")
    worker = start_temporary_vector_worker(log_dir=data_dir / "logs")
    try:
        assert worker.manager.base_url is not None
        response = httpx.post(
            f"{worker.manager.base_url}/create-collection",
            json={"anima_name": "worker_smoke", "collection": "worker_smoke_knowledge"},
            timeout=10.0,
        )
        assert response.status_code == 409
        assert response.json() == {"detail": "Vector worker disabled for phase3 anima: worker_smoke"}
    finally:
        worker.stop()
