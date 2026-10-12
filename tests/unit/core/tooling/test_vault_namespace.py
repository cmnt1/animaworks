from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.vault import VaultManager
from core.exceptions import ConfigError


def _make_handler(tmp_path: Path):
    anima_dir = tmp_path / "animas" / "sakura"
    (anima_dir / "activity_log").mkdir(parents=True)
    memory = MagicMock()
    memory.anima_dir = anima_dir
    with (
        patch("core.tooling.handler.ExternalToolDispatcher"),
        patch("core.config.models.load_config", side_effect=ConfigError("skip")),
    ):
        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir=anima_dir, memory=memory)
    return handler


def _make_vault(tmp_path: Path) -> VaultManager:
    vault = VaultManager(tmp_path)
    vault.generate_key()
    vault.store("sakura", "OWN_SECRET", "own-value")
    vault.store("shared", "SHARED_SECRET", "shared-value")
    vault.store("alice", "FOREIGN_SECRET", "foreign-value")
    return vault


def test_vault_get_rejects_foreign_namespace_and_allows_own_and_shared(tmp_path: Path) -> None:
    handler = _make_handler(tmp_path)
    vault = _make_vault(tmp_path)

    with patch("core.config.vault.get_vault_manager", return_value=vault):
        foreign = json.loads(handler.handle("vault_get", {"section": "alice", "key": "FOREIGN_SECRET"}))
        own = handler.handle("vault_get", {"section": "sakura", "key": "OWN_SECRET"})
        shared = handler.handle("vault_get", {"section": "shared", "key": "SHARED_SECRET"})

    assert foreign["status"] == "error"
    assert foreign["error_type"] == "PermissionDenied"
    assert own == "own-value"
    assert shared == "shared-value"


def test_vault_get_without_section_searches_only_own_then_shared(tmp_path: Path) -> None:
    handler = _make_handler(tmp_path)
    vault = _make_vault(tmp_path)

    with patch("core.config.vault.get_vault_manager", return_value=vault):
        own = handler.handle("vault_get", {"key": "OWN_SECRET"})
        shared = handler.handle("vault_get", {"key": "SHARED_SECRET"})
        foreign = json.loads(handler.handle("vault_get", {"key": "FOREIGN_SECRET"}))

    assert own == "own-value"
    assert shared == "shared-value"
    assert foreign["status"] == "error"
    assert foreign["error_type"] == "NotFound"


def test_vault_list_hides_foreign_namespaces_and_store_is_own_only(tmp_path: Path) -> None:
    handler = _make_handler(tmp_path)
    vault = _make_vault(tmp_path)

    with patch("core.config.vault.get_vault_manager", return_value=vault):
        listed = json.loads(handler.handle("vault_list", {}))
        foreign_list = json.loads(handler.handle("vault_list", {"section": "alice"}))
        own_store = json.loads(handler.handle("vault_store", {"key": "NEW_KEY", "value": "new-value"}))
        shared_store = json.loads(
            handler.handle("vault_store", {"section": "shared", "key": "NEW_SECRET", "value": "new-value"})
        )

    assert listed == {
        "sections": {"sakura": ["OWN_SECRET"], "shared": ["SHARED_SECRET"]},
    }
    assert foreign_list["status"] == "error"
    assert foreign_list["error_type"] == "PermissionDenied"
    assert own_store["status"] == "ok"
    assert vault.get("sakura", "NEW_KEY") == "new-value"
    assert shared_store["status"] == "error"
    assert shared_store["error_type"] == "PermissionDenied"
    assert vault.get("shared", "NEW_SECRET") is None
