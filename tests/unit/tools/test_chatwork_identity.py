"""Tests for Chatwork identity resolution and account-specific caches."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.config.schemas import AnimaWorksConfig, ChatworkToolConfig
from core.exceptions import ToolConfigError
from core.tools._chatwork_cache import resolve_cache_db_path
from core.tools._chatwork_identity import (
    ChatworkIdentity,
    check_write_allowed,
    resolve_identity,
)


def _config(grants: dict[str, dict[str, str]]) -> AnimaWorksConfig:
    return AnimaWorksConfig(chatwork_tool=ChatworkToolConfig(grants=grants))


def test_primary_identity_uses_anima_dir_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", "/srv/animas/mei")
    with patch(
        "core.tools._chatwork_identity.resolve_env_style_credential",
        return_value="mei-token",
    ) as resolver:
        identity = resolve_identity()

    assert identity == ChatworkIdentity(name="mei", token="mei-token")
    resolver.assert_called_once_with("CHATWORK_API_TOKEN__mei")


def test_primary_identity_explicit_anima_dir_precedes_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", "/srv/animas/other")
    with patch(
        "core.tools._chatwork_identity.resolve_env_style_credential",
        return_value="kotoha-token",
    ) as resolver:
        identity = resolve_identity(anima_dir="/srv/animas/kotoha")

    assert identity.name == "kotoha"
    resolver.assert_called_once_with("CHATWORK_API_TOKEN__kotoha")


def test_missing_primary_token_does_not_fall_back_to_legacy_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", "/srv/animas/mei")
    monkeypatch.setenv("CHATWORK_API_TOKEN", "legacy-read-token")
    monkeypatch.setenv("CHATWORK_API_TOKEN_WRITE", "legacy-write-token")
    monkeypatch.setenv("CHATWORK_API_TOKEN_WRITE__mei", "legacy-per-anima-token")
    with patch(
        "core.tools._chatwork_identity.resolve_env_style_credential",
        return_value=None,
    ) as resolver, pytest.raises(ToolConfigError, match="CHATWORK_API_TOKEN__mei"):
        resolve_identity()

    resolver.assert_called_once_with("CHATWORK_API_TOKEN__mei")


def test_read_grant_allows_resolution_but_rejects_write() -> None:
    config = _config({"mei": {"owner": "read"}})
    with (
        patch("core.config.models.load_config", return_value=config),
        patch(
            "core.tools._chatwork_identity.resolve_env_style_credential",
            return_value="owner-token",
        ),
    ):
        identity = resolve_identity("owner", anima_dir="/srv/animas/mei")
        with pytest.raises(ToolConfigError, match="read-only"):
            check_write_allowed("owner", anima_dir="/srv/animas/mei")

    assert identity == ChatworkIdentity(name="owner", token="owner-token")


def test_readwrite_grant_allows_write() -> None:
    config = _config({"mei": {"owner": "readwrite"}})
    with (
        patch("core.config.models.load_config", return_value=config),
        patch(
            "core.tools._chatwork_identity.resolve_env_style_credential",
            return_value="owner-token",
        ),
    ):
        assert resolve_identity("owner", anima_dir="/srv/animas/mei").name == "owner"
        check_write_allowed("owner", anima_dir="/srv/animas/mei")


def test_missing_grant_rejects_delegated_identity() -> None:
    with (
        patch("core.config.models.load_config", return_value=_config({})),
        patch("core.tools._chatwork_identity.resolve_env_style_credential") as resolver,
        pytest.raises(ToolConfigError, match="has not been delegated"),
    ):
        resolve_identity("owner", anima_dir="/srv/animas/mei")

    resolver.assert_not_called()


def test_no_anima_context_uses_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANIMAWORKS_ANIMA_DIR", raising=False)
    with patch(
        "core.tools._chatwork_identity.resolve_env_style_credential",
        return_value="owner-token",
    ) as resolver:
        identity = resolve_identity()

    assert identity == ChatworkIdentity(name="owner", token="owner-token")
    resolver.assert_called_once_with("CHATWORK_API_TOKEN__owner")


def test_primary_identity_is_always_write_allowed() -> None:
    with patch("core.config.models.load_config") as load_config:
        check_write_allowed(None, anima_dir="/srv/animas/mei")
    load_config.assert_not_called()


def test_cache_paths_are_split_by_account_and_map_hits_skip_me(tmp_path) -> None:
    first = SimpleNamespace(api_token="token-a", me=MagicMock(return_value={"account_id": 101}))
    second = SimpleNamespace(api_token="token-b", me=MagicMock(return_value={"account_id": 202}))

    with patch("core.tools._chatwork_cache.DEFAULT_CACHE_DIR", tmp_path):
        first_path = resolve_cache_db_path(first)
        second_path = resolve_cache_db_path(second)

        cached = SimpleNamespace(api_token="token-a", me=MagicMock())
        cached_path = resolve_cache_db_path(cached)

    assert first_path == tmp_path / "101" / "messages.db"
    assert second_path == tmp_path / "202" / "messages.db"
    assert cached_path == first_path
    first.me.assert_called_once_with()
    second.me.assert_called_once_with()
    cached.me.assert_not_called()


def test_cli_read_only_delegation_rejects_write_before_client_creation(capsys) -> None:
    from core.tools._chatwork_cli import cli_main

    with (
        patch(
            "core.tools._chatwork_cli.resolve_identity",
            return_value=ChatworkIdentity(name="owner", token="owner-token"),
        ),
        patch(
            "core.tools._chatwork_cli.check_write_allowed",
            side_effect=ToolConfigError(
                "Delegation to identity owner is read-only; write operations are not allowed."
            ),
        ),
        patch("core.tools._chatwork_cli.ChatworkClient") as client_class,
        pytest.raises(SystemExit) as exc_info,
    ):
        cli_main(["send", "123", "hello", "--as", "owner"])

    assert exc_info.value.code == 1
    assert "write operations are not allowed" in capsys.readouterr().err
    client_class.assert_not_called()


def test_cli_read_command_accepts_as_identity(capsys) -> None:
    from core.tools._chatwork_cli import cli_main

    client = MagicMock()
    client.me.return_value = {"account_id": 42, "name": "Owner"}
    with (
        patch(
            "core.tools._chatwork_cli.resolve_identity",
            return_value=ChatworkIdentity(name="owner", token="owner-token"),
        ) as resolver,
        patch("core.tools._chatwork_cli.ChatworkClient", return_value=client) as client_class,
    ):
        cli_main(["me", "--as", "owner"])

    resolver.assert_called_once_with("owner")
    client_class.assert_called_once_with(api_token="owner-token")
    assert "Account ID: 42" in capsys.readouterr().out
