"""Unit tests for server/app.py — FastAPI app factory and lifespan."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── create_app ───────────────────────────────────────────


class TestCreateApp:
    """Tests for create_app factory."""

    @patch("core.paths.get_data_dir")
    @patch("server.app.load_config")
    @patch("server.app.ProcessSupervisor")
    @patch("server.app.WebSocketManager")
    def test_create_app_no_persons_dir(
        self, mock_ws_cls, mock_sup_cls, mock_load_config, mock_get_data_dir, tmp_path
    ):
        from server.app import create_app

        persons_dir = tmp_path / "persons"
        shared_dir = tmp_path / "shared"
        # persons_dir does not exist

        mock_ws_cls.return_value = MagicMock()
        mock_sup_cls.return_value = MagicMock()
        mock_load_config.return_value = MagicMock(setup_complete=True)
        mock_get_data_dir.return_value = tmp_path

        app = create_app(persons_dir, shared_dir)

        assert app.state.person_names == []
        assert app.state.persons_dir == persons_dir
        assert app.state.shared_dir == shared_dir

    @patch("core.paths.get_data_dir")
    @patch("server.app.load_config")
    @patch("server.app.ProcessSupervisor")
    @patch("server.app.WebSocketManager")
    def test_create_app_with_persons(
        self, mock_ws_cls, mock_sup_cls, mock_load_config, mock_get_data_dir, tmp_path
    ):
        from server.app import create_app

        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        # Create a fake person directory with identity.md
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir()
        (alice_dir / "identity.md").write_text("# Alice", encoding="utf-8")

        mock_ws_cls.return_value = MagicMock()
        mock_sup_cls.return_value = MagicMock()
        mock_load_config.return_value = MagicMock(setup_complete=True)
        mock_get_data_dir.return_value = tmp_path

        app = create_app(persons_dir, shared_dir)

        assert "alice" in app.state.person_names

    @patch("core.paths.get_data_dir")
    @patch("server.app.load_config")
    @patch("server.app.ProcessSupervisor")
    @patch("server.app.WebSocketManager")
    def test_create_app_skips_dirs_without_identity(
        self, mock_ws_cls, mock_sup_cls, mock_load_config, mock_get_data_dir, tmp_path
    ):
        from server.app import create_app

        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        # Create dir without identity.md
        (persons_dir / "invalid").mkdir()

        mock_ws_cls.return_value = MagicMock()
        mock_sup_cls.return_value = MagicMock()
        mock_load_config.return_value = MagicMock(setup_complete=True)
        mock_get_data_dir.return_value = tmp_path

        app = create_app(persons_dir, shared_dir)

        assert app.state.person_names == []

    @patch("core.paths.get_data_dir")
    @patch("server.app.load_config")
    @patch("server.app.ProcessSupervisor")
    @patch("server.app.WebSocketManager")
    def test_create_app_skips_files_in_persons_dir(
        self, mock_ws_cls, mock_sup_cls, mock_load_config, mock_get_data_dir, tmp_path
    ):
        from server.app import create_app

        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        # Create a file (not a directory)
        (persons_dir / "not_a_dir.txt").write_text("hello", encoding="utf-8")

        mock_ws_cls.return_value = MagicMock()
        mock_sup_cls.return_value = MagicMock()
        mock_load_config.return_value = MagicMock(setup_complete=True)
        mock_get_data_dir.return_value = tmp_path

        app = create_app(persons_dir, shared_dir)

        assert app.state.person_names == []

    @patch("core.paths.get_data_dir")
    @patch("server.app.load_config")
    @patch("server.app.ProcessSupervisor")
    @patch("server.app.WebSocketManager")
    def test_create_app_skips_disabled_person(
        self, mock_ws_cls, mock_sup_cls, mock_load_config, mock_get_data_dir, tmp_path
    ):
        """Person with status.json enabled:false is excluded from person_names."""
        import json
        from server.app import create_app

        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        # Enabled person
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir()
        (alice_dir / "identity.md").write_text("# Alice", encoding="utf-8")
        (alice_dir / "status.json").write_text(
            json.dumps({"enabled": True}), encoding="utf-8"
        )

        # Disabled person
        bob_dir = persons_dir / "bob"
        bob_dir.mkdir()
        (bob_dir / "identity.md").write_text("# Bob", encoding="utf-8")
        (bob_dir / "status.json").write_text(
            json.dumps({"enabled": False}), encoding="utf-8"
        )

        mock_ws_cls.return_value = MagicMock()
        mock_sup_cls.return_value = MagicMock()
        mock_load_config.return_value = MagicMock(setup_complete=True)
        mock_get_data_dir.return_value = tmp_path

        app = create_app(persons_dir, shared_dir)

        assert "alice" in app.state.person_names
        assert "bob" not in app.state.person_names


# ── lifespan ─────────────────────────────────────────────


class TestLifespan:
    """Tests for the lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_start_and_stop(self):
        from server.app import lifespan

        mock_app = MagicMock()
        mock_supervisor = AsyncMock()
        mock_app.state.setup_complete = True
        mock_app.state.supervisor = mock_supervisor
        mock_app.state.person_names = ["alice"]

        async with lifespan(mock_app):
            mock_supervisor.start_all.assert_awaited_once_with(["alice"])

        mock_supervisor.shutdown_all.assert_awaited_once()
