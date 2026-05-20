from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.memory.rag.vector_worker_client import VectorWorkerManager


class _ExitedProcess:
    returncode = -11

    def poll(self) -> int:
        return self.returncode


def test_vector_worker_segfault_records_rag_corruption(tmp_path: Path) -> None:
    manager = VectorWorkerManager(
        enabled=True,
        host="127.0.0.1",
        port=0,
        log_dir=tmp_path,
    )
    manager.process = _ExitedProcess()  # type: ignore[assignment]

    with patch("core.memory.rag.repair.record_chroma_error") as record:
        manager._record_crash_if_exited(  # noqa: SLF001
            {"anima_name": "sora", "collection": "sora_knowledge"}
        )

    record.assert_called_once_with(
        anima_name="sora",
        collection="sora_knowledge",
        error=-11,
        source="vector_worker",
    )
    assert manager.process is None
    assert manager.native_crash_detected is True


def test_vector_worker_config_defaults_do_not_direct_fallback(tmp_path: Path) -> None:
    manager = VectorWorkerManager.from_config(
        SimpleNamespace(rag=SimpleNamespace()),
        log_dir=tmp_path,
    )

    assert manager.fallback_direct is False
