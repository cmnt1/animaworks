from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.memory.rag.repair import RepairResult


def test_rag_startup_preflight_repairs_suspects() -> None:
    from cli.commands.server import _run_rag_startup_preflight

    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = ["sora"]
    service.repair_animas_if_allowed.return_value = {
        "sora": RepairResult(status="success", anima_name="sora", reason="startup_chroma_crash_preflight")
    }

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
    ):
        _run_rag_startup_preflight()

    service.discover_suspect_animas.assert_called_once_with(window_minutes=30)
    service.repair_animas_if_allowed.assert_called_once_with(
        ["sora"],
        reason="startup_chroma_crash_preflight",
        source="startup_preflight",
        include_shared=True,
    )


def test_rag_startup_preflight_repairs_vectordbs_after_unclean_exit(data_dir: Path) -> None:
    from cli.commands.server import _run_rag_startup_preflight

    anima_dir = data_dir / "animas" / "sora"
    (anima_dir / "state").mkdir(parents=True)
    (anima_dir / "identity.md").write_text("# sora", encoding="utf-8")
    (anima_dir / "vectordb").mkdir()
    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = []
    service.list_repairable_animas.return_value = ["sora"]
    service.repair_animas_if_allowed.return_value = {
        "sora": RepairResult(status="success", anima_name="sora", reason="startup_unclean_exit_preflight")
    }

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
    ):
        _run_rag_startup_preflight(force_all_vectordb=True)

    service.repair_animas_if_allowed.assert_called_once_with(
        ["sora"],
        reason="startup_unclean_exit_preflight",
        source="startup_preflight",
        include_shared=True,
    )


def test_rag_startup_preflight_worker_skipped_without_suspects() -> None:
    from cli.commands.server import _run_rag_startup_preflight_via_worker

    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
            vector_worker_enabled=True,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = []

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
        patch("core.memory.rag.vector_worker_client.start_temporary_vector_worker") as mock_worker,
    ):
        _run_rag_startup_preflight_via_worker()

    mock_worker.assert_not_called()
    service.repair_animas_if_allowed.assert_not_called()


def test_rag_startup_preflight_worker_skipped_when_all_targets_blocked() -> None:
    from cli.commands.server import _run_rag_startup_preflight_via_worker

    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
            vector_worker_enabled=True,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = ["sora"]
    service.repair_blocker.return_value = RepairResult(
        status="cooldown",
        anima_name="sora",
        reason="startup_chroma_crash_preflight",
    )

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
        patch("core.memory.rag.vector_worker_client.start_temporary_vector_worker") as mock_worker,
    ):
        _run_rag_startup_preflight_via_worker()

    mock_worker.assert_not_called()
    service.repair_animas_if_allowed.assert_not_called()


def test_rag_startup_preflight_worker_starts_for_unblocked_targets() -> None:
    from cli.commands.server import _run_rag_startup_preflight_via_worker

    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
            vector_worker_enabled=True,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = ["sora"]
    service.repair_blocker.return_value = None
    service.repair_animas_if_allowed.return_value = {
        "sora": RepairResult(status="success", anima_name="sora", reason="startup_chroma_crash_preflight")
    }
    worker = MagicMock()

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
        patch("core.memory.rag.vector_worker_client.start_temporary_vector_worker", return_value=worker) as mock_worker,
    ):
        _run_rag_startup_preflight_via_worker()

    mock_worker.assert_called_once()
    assert mock_worker.call_args.kwargs["config"] is config
    assert mock_worker.call_args.kwargs["log_dir"].name == "logs"
    service.repair_animas_if_allowed.assert_called_once_with(
        ["sora"],
        reason="startup_chroma_crash_preflight",
        source="startup_preflight",
        include_shared=True,
    )
    worker.stop.assert_called_once()
