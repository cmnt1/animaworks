# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Chatwork cache path resolution under a read-only cache dir."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.integrations import _chatwork_cache, _slack_cache


@pytest.fixture
def client() -> SimpleNamespace:
    return SimpleNamespace(api_token="token-abc", me=lambda: {"account_id": 4242})


def test_chatwork_cache_dir_reads_environment_each_time(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first-cache"
    second = tmp_path / "second-cache"
    monkeypatch.setenv("ANIMAWORKS_CHATWORK_CACHE_DIR", str(first))
    assert _chatwork_cache.get_cache_dir() == first
    monkeypatch.setenv("ANIMAWORKS_CHATWORK_CACHE_DIR", str(second))
    assert _chatwork_cache.get_cache_dir() == second


def test_slack_cache_dir_reads_environment_each_time(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first-slack-cache"
    second = tmp_path / "second-slack-cache"
    monkeypatch.setenv("ANIMAWORKS_SLACK_CACHE_DIR", str(first))
    assert _slack_cache.get_cache_dir() == first
    monkeypatch.setenv("ANIMAWORKS_SLACK_CACHE_DIR", str(second))
    assert _slack_cache.get_cache_dir() == second


def test_default_cache_dirs_follow_current_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ANIMAWORKS_CHATWORK_CACHE_DIR", raising=False)
    monkeypatch.delenv("ANIMAWORKS_SLACK_CACHE_DIR", raising=False)
    data_dir = tmp_path / "isolated-data"
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))

    assert _chatwork_cache.get_cache_dir() == data_dir / "cache" / "chatwork"
    assert _slack_cache.get_cache_dir() == data_dir / "cache" / "slack"


def test_resolve_cache_db_path_registers_identity(tmp_path: Path, monkeypatch, client) -> None:
    cache_dir = tmp_path / "chatwork"
    monkeypatch.setattr(_chatwork_cache, "DEFAULT_CACHE_DIR", cache_dir)

    db_path = _chatwork_cache.resolve_cache_db_path(client)

    assert db_path == cache_dir / "4242" / "messages.db"
    identity_map = json.loads((cache_dir / "identity_map.json").read_text(encoding="utf-8"))
    assert list(identity_map.values()) == ["4242"]


@pytest.mark.skipif(os.name == "nt", reason="chmod read-only is a no-op on Windows")
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
