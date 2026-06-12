from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.memory.rag.vector_worker_client import (
    VectorWorkerManager,
    cleanup_orphaned_vector_workers,
    start_temporary_vector_worker,
)


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


def test_vector_worker_subprocess_env_allows_direct_chroma(tmp_path: Path) -> None:
    manager = VectorWorkerManager(
        enabled=True,
        host="127.0.0.1",
        port=12345,
        log_dir=tmp_path,
    )

    async def fake_wait() -> None:
        return None

    with (
        patch("subprocess.Popen") as popen,
        patch.object(manager, "_wait_until_healthy", side_effect=fake_wait),
    ):
        import asyncio

        asyncio.run(manager._start_process())  # noqa: SLF001

    env = popen.call_args.kwargs["env"]
    assert env["ANIMAWORKS_ALLOW_DIRECT_CHROMA"] == "1"
    assert "ANIMAWORKS_VECTOR_URL" not in env


def test_start_temporary_vector_worker_sets_and_restores_vector_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANIMAWORKS_VECTOR_URL", "http://previous/vector")

    async def fake_ensure_running(self, *, payload=None) -> None:
        self.base_url = "http://127.0.0.1:45678"

    with (
        patch.object(VectorWorkerManager, "_ensure_running", new=fake_ensure_running),
        patch.object(VectorWorkerManager, "stop", new=AsyncMock()),
    ):
        worker = start_temporary_vector_worker(
            config=SimpleNamespace(rag=SimpleNamespace(vector_worker_enabled=True)),
            log_dir=tmp_path,
        )

        assert os.environ["ANIMAWORKS_VECTOR_URL"] == "http://127.0.0.1:45678"
        worker.stop()

    assert os.environ["ANIMAWORKS_VECTOR_URL"] == "http://previous/vector"


def test_cleanup_orphaned_vector_workers_kills_only_parentless_workers(monkeypatch) -> None:
    from core.paths import PROJECT_DIR

    class FakeProcess:
        def __init__(self, pid: int, ppid: int, cmdline: list[str]) -> None:
            self.info = {
                "pid": pid,
                "ppid": ppid,
                "cmdline": cmdline,
                "exe": "python.exe",
                "name": "python.exe",
            }
            self.killed = False

        def cwd(self) -> str:
            return str(PROJECT_DIR)

        def children(self, recursive: bool = False) -> list[FakeProcess]:
            return []

        def parents(self) -> list[FakeProcess]:
            return []

        def kill(self) -> None:
            self.killed = True

    orphan = FakeProcess(1001, 9001, ["python", "-m", "core.memory.rag.vector_worker"])
    live_child = FakeProcess(1002, 9002, ["python", "-m", "core.memory.rag.vector_worker"])

    monkeypatch.setattr("core.memory.rag.vector_worker_client.psutil.process_iter", lambda attrs: [orphan, live_child])
    monkeypatch.setattr(
        "core.memory.rag.vector_worker_client.psutil.pid_exists",
        lambda pid: pid == 9002,
    )

    assert cleanup_orphaned_vector_workers() == 1
    assert orphan.killed is True
    assert live_child.killed is False
