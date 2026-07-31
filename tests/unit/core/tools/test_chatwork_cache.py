# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Chatwork cache path resolution under a read-only cache dir."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.tools import _chatwork_cache


@pytest.fixture
def client() -> SimpleNamespace:
    return SimpleNamespace(api_token="token-abc", me=lambda: {"account_id": 4242})


def test_resolve_cache_db_path_registers_identity(tmp_path: Path, monkeypatch, client) -> None:
    cache_dir = tmp_path / "chatwork"
    monkeypatch.setattr(_chatwork_cache, "DEFAULT_CACHE_DIR", cache_dir)

    db_path = _chatwork_cache.resolve_cache_db_path(client)

    assert db_path == cache_dir / "4242" / "messages.db"
    identity_map = json.loads((cache_dir / "identity_map.json").read_text(encoding="utf-8"))
    assert list(identity_map.values()) == ["4242"]


def test_resolve_cache_db_path_survives_read_only_cache(tmp_path: Path, monkeypatch, client) -> None:
    """A read-only sandbox must not turn an identity lookup into a hard error."""
    cache_dir = tmp_path / "chatwork"
    cache_dir.mkdir()
    cache_dir.chmod(0o500)
    monkeypatch.setattr(_chatwork_cache, "DEFAULT_CACHE_DIR", cache_dir)

    try:
        db_path = _chatwork_cache.resolve_cache_db_path(client)
    finally:
        cache_dir.chmod(0o700)

    assert db_path == cache_dir / "4242" / "messages.db"
    assert not (cache_dir / "identity_map.json").exists()
