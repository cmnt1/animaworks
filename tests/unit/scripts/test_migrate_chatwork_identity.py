"""Unit tests for scripts/migrate_chatwork_identity.py (temp dirs only)."""

from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.vault import VaultManager
from scripts.migrate_chatwork_identity import (
    _DEFAULT_GRANTS,
    main,
    run_migration,
)


def _fp(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _seed_legacy_vault(data_dir: Path) -> VaultManager:
    vault = VaultManager(data_dir)
    vault.store("shared", "CHATWORK_API_TOKEN", "legacy-owner-token")
    vault.store("shared", "CHATWORK_API_TOKEN_WRITE", "legacy-kotoha-token")
    vault.store("shared", "CHATWORK_API_TOKEN_WRITE__mei", "legacy-mei-token")
    return vault


def test_dry_run_makes_no_changes(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vault = _seed_legacy_vault(data_dir)
    config_path = data_dir / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    old_db = cache_dir / "messages.db"
    old_db.write_text("legacy-db", encoding="utf-8")
    haato_file = data_dir / "credentials" / "hhc-chatwork-bot-token"
    haato_file.parent.mkdir(parents=True)
    haato_file.write_text("  haato-bot-token  \n", encoding="utf-8")

    before_vault = {
        "CHATWORK_API_TOKEN": vault.get("shared", "CHATWORK_API_TOKEN"),
        "CHATWORK_API_TOKEN_WRITE": vault.get("shared", "CHATWORK_API_TOKEN_WRITE"),
        "CHATWORK_API_TOKEN_WRITE__mei": vault.get(
            "shared", "CHATWORK_API_TOKEN_WRITE__mei"
        ),
    }
    before_config = config_path.read_text(encoding="utf-8")
    before_db = old_db.read_text(encoding="utf-8")

    rc = run_migration(
        data_dir=data_dir,
        cache_dir=cache_dir,
        apply=False,
        finalize=False,
        vault=vault,
    )
    assert rc == 0

    assert vault.get("shared", "CHATWORK_API_TOKEN__owner") is None
    assert vault.get("shared", "CHATWORK_API_TOKEN__kotoha") is None
    assert vault.get("shared", "CHATWORK_API_TOKEN__mei") is None
    assert vault.get("shared", "CHATWORK_API_TOKEN__haato_ai") is None
    for key, value in before_vault.items():
        assert vault.get("shared", key) == value
    assert config_path.read_text(encoding="utf-8") == before_config
    assert old_db.read_text(encoding="utf-8") == before_db
    assert not (cache_dir / "identity_map.json").exists()


def test_apply_copies_grants_and_is_idempotent(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vault = _seed_legacy_vault(data_dir)
    config_path = data_dir / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "messages.db").write_text("legacy-db", encoding="utf-8")
    haato_file = data_dir / "credentials" / "hhc-chatwork-bot-token"
    haato_file.parent.mkdir(parents=True)
    haato_file.write_text("haato-bot-token\n", encoding="utf-8")

    mock_client = MagicMock()
    mock_client.me.return_value = {"account_id": 4242}

    with patch(
        "core.tools._chatwork_client.ChatworkClient",
        return_value=mock_client,
    ):
        # First apply
        rc = run_migration(
            data_dir=data_dir,
            cache_dir=cache_dir,
            apply=True,
            finalize=False,
            vault=vault,
        )
    assert rc == 0

    assert vault.get("shared", "CHATWORK_API_TOKEN__owner") == "legacy-owner-token"
    assert vault.get("shared", "CHATWORK_API_TOKEN__kotoha") == "legacy-kotoha-token"
    assert vault.get("shared", "CHATWORK_API_TOKEN__mei") == "legacy-mei-token"
    assert vault.get("shared", "CHATWORK_API_TOKEN__haato_ai") == "haato-bot-token"
    # Legacy keys remain until finalize
    assert vault.get("shared", "CHATWORK_API_TOKEN") == "legacy-owner-token"
    assert vault.get("shared", "CHATWORK_API_TOKEN_WRITE") == "legacy-kotoha-token"

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    assert cfg["chatwork_tool"]["grants"] == _DEFAULT_GRANTS

    dest = cache_dir / "4242" / "messages.db"
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "legacy-db"
    assert not (cache_dir / "messages.db").exists()
    identity_map = json.loads((cache_dir / "identity_map.json").read_text(encoding="utf-8"))
    assert identity_map[_fp("legacy-owner-token")] == "4242"

    # Snapshot for idempotency
    vault_snapshot = {
        k: vault.get("shared", k)
        for k in (
            "CHATWORK_API_TOKEN",
            "CHATWORK_API_TOKEN_WRITE",
            "CHATWORK_API_TOKEN_WRITE__mei",
            "CHATWORK_API_TOKEN__owner",
            "CHATWORK_API_TOKEN__kotoha",
            "CHATWORK_API_TOKEN__mei",
            "CHATWORK_API_TOKEN__haato_ai",
        )
    }
    config_snapshot = config_path.read_text(encoding="utf-8")
    map_snapshot = (cache_dir / "identity_map.json").read_text(encoding="utf-8")
    db_snapshot = dest.read_text(encoding="utf-8")

    # Second apply must be a no-op
    rc2 = run_migration(
        data_dir=data_dir,
        cache_dir=cache_dir,
        apply=True,
        finalize=False,
        vault=vault,
    )
    assert rc2 == 0
    for k, v in vault_snapshot.items():
        assert vault.get("shared", k) == v
    assert config_path.read_text(encoding="utf-8") == config_snapshot
    assert (cache_dir / "identity_map.json").read_text(encoding="utf-8") == map_snapshot
    assert dest.read_text(encoding="utf-8") == db_snapshot


def test_apply_skips_existing_dest_and_existing_grants(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vault = _seed_legacy_vault(data_dir)
    vault.store("shared", "CHATWORK_API_TOKEN__owner", "already-owner")
    config_path = data_dir / "config.json"
    custom_grants = {"sakura": {"owner": "readwrite"}}
    config_path.write_text(
        json.dumps({"chatwork_tool": {"grants": custom_grants}}, indent=2) + "\n",
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    rc = run_migration(
        data_dir=data_dir,
        cache_dir=cache_dir,
        apply=True,
        finalize=False,
        vault=vault,
    )
    assert rc == 0
    # Destination not overwritten
    assert vault.get("shared", "CHATWORK_API_TOKEN__owner") == "already-owner"
    # Other copies still happen
    assert vault.get("shared", "CHATWORK_API_TOKEN__kotoha") == "legacy-kotoha-token"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    assert cfg["chatwork_tool"]["grants"] == custom_grants


def test_finalize_deletes_legacy_keys(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vault = _seed_legacy_vault(data_dir)
    # Ensure identity keys exist first (as production would after apply)
    vault.store("shared", "CHATWORK_API_TOKEN__owner", "legacy-owner-token")
    vault.store("shared", "CHATWORK_API_TOKEN__kotoha", "legacy-kotoha-token")
    vault.store("shared", "CHATWORK_API_TOKEN__mei", "legacy-mei-token")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    rc = run_migration(
        data_dir=data_dir,
        cache_dir=cache_dir,
        apply=True,
        finalize=True,
        vault=vault,
    )
    assert rc == 0
    assert vault.get("shared", "CHATWORK_API_TOKEN") is None
    assert vault.get("shared", "CHATWORK_API_TOKEN_WRITE") is None
    assert vault.get("shared", "CHATWORK_API_TOKEN_WRITE__mei") is None
    assert vault.get("shared", "CHATWORK_API_TOKEN__owner") == "legacy-owner-token"
    assert vault.get("shared", "CHATWORK_API_TOKEN__kotoha") == "legacy-kotoha-token"
    assert vault.get("shared", "CHATWORK_API_TOKEN__mei") == "legacy-mei-token"


def test_cache_migrate_skips_when_api_fails(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vault = VaultManager(data_dir)
    vault.store("shared", "CHATWORK_API_TOKEN__owner", "owner-token")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    old_db = cache_dir / "messages.db"
    old_db.write_text("legacy-db", encoding="utf-8")

    mock_client = MagicMock()
    mock_client.me.side_effect = RuntimeError("network down")

    with patch(
        "core.tools._chatwork_client.ChatworkClient",
        return_value=mock_client,
    ):
        rc = run_migration(
            data_dir=data_dir,
            cache_dir=cache_dir,
            apply=True,
            finalize=False,
            vault=vault,
        )
    assert rc == 0
    assert old_db.is_file()
    assert not (cache_dir / "identity_map.json").exists()


def test_cli_dry_run_default_exits_zero(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    rc = main(
        [
            "--data-dir",
            str(data_dir),
            "--cache-dir",
            str(cache_dir),
        ]
    )
    assert rc == 0
