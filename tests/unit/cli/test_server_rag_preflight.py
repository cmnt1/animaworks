from __future__ import annotations

import os
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
            quick_check_timeout_seconds=4.0,
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

    service.discover_suspect_animas.assert_called_once_with(
        window_minutes=30,
        quick_check_timeout_seconds=4.0,
        quick_check_source="startup_quick_check",
    )
    service.repair_animas_if_allowed.assert_called_once_with(
        ["sora"],
        reason="startup_chroma_crash_preflight",
        source="startup_preflight",
        include_shared=True,
    )


def test_rag_startup_preflight_sets_repair_nonce_during_repair(monkeypatch) -> None:
    """Regression: preflight must set ANIMAWORKS_RAG_REPAIR_NONCE for worker verify."""
    from cli.commands.server import _run_rag_startup_preflight

    monkeypatch.delenv("ANIMAWORKS_RAG_REPAIR_NONCE", raising=False)

    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
            quick_check_timeout_seconds=4.0,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = ["mei"]
    nonce_at_call: dict[str, str | None] = {}

    def _capture_nonce(*_args, **_kwargs):
        nonce_at_call["value"] = os.environ.get("ANIMAWORKS_RAG_REPAIR_NONCE")
        return {
            "mei": RepairResult(
                status="success",
                anima_name="mei",
                reason="startup_chroma_crash_preflight",
            )
        }

    service.repair_animas_if_allowed.side_effect = _capture_nonce

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
    ):
        _run_rag_startup_preflight()

    assert nonce_at_call["value"], "repair nonce must be set while repair_animas_if_allowed runs"
    assert os.environ.get("ANIMAWORKS_RAG_REPAIR_NONCE") is None, "nonce must be restored after preflight"


def test_rag_startup_preflight_preserves_existing_repair_nonce(monkeypatch) -> None:
    from cli.commands.server import _run_rag_startup_preflight

    monkeypatch.setenv("ANIMAWORKS_RAG_REPAIR_NONCE", "pre-existing-nonce")

    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
            quick_check_timeout_seconds=4.0,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = ["mei"]
    nonce_at_call: dict[str, str | None] = {}

    def _capture_nonce(*_args, **_kwargs):
        nonce_at_call["value"] = os.environ.get("ANIMAWORKS_RAG_REPAIR_NONCE")
        return {
            "mei": RepairResult(
                status="success",
                anima_name="mei",
                reason="startup_chroma_crash_preflight",
            )
        }

    service.repair_animas_if_allowed.side_effect = _capture_nonce

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
    ):
        _run_rag_startup_preflight()

    assert nonce_at_call["value"] == "pre-existing-nonce"
    assert os.environ.get("ANIMAWORKS_RAG_REPAIR_NONCE") == "pre-existing-nonce"


def test_rag_startup_preflight_ignores_unclean_exit_without_suspects() -> None:
    from cli.commands.server import _run_rag_startup_preflight

    config = SimpleNamespace(
        setup_complete=True,
        rag=SimpleNamespace(
            repair_enabled=True,
            startup_repair_preflight_enabled=True,
            startup_repair_window_minutes=30,
            quick_check_timeout_seconds=4.0,
        ),
    )
    service = MagicMock()
    service.discover_suspect_animas.return_value = []

    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
    ):
        _run_rag_startup_preflight(force_all_vectordb=True)

    service.list_repairable_animas.assert_not_called()
    service.repair_animas_if_allowed.assert_not_called()
