"""Shared Google OAuth behavior and credential resolver integration tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("google.oauth2.credentials")
pytest.importorskip("google_auth_oauthlib.flow")

from core.integrations.gmail import GmailClient
from core.integrations.google_calendar import GoogleCalendarClient
from core.integrations.google_sheets import GoogleSheetsClient
from core.integrations.google_tasks import GoogleTasksClient

_CLIENTS = [
    pytest.param(
        GmailClient,
        [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
        "GMAIL",
        ValueError,
        "No OAuth credentials found. Place credentials.json or set GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET.",
        id="gmail",
    ),
    pytest.param(
        GoogleCalendarClient,
        [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ],
        "GOOGLE_CALENDAR",
        FileNotFoundError,
        "calendar",
        id="calendar",
    ),
    pytest.param(
        GoogleTasksClient,
        ["https://www.googleapis.com/auth/tasks"],
        "GOOGLE_TASKS",
        FileNotFoundError,
        "tasks",
        id="tasks",
    ),
    pytest.param(
        GoogleSheetsClient,
        ["https://www.googleapis.com/auth/spreadsheets"],
        None,
        FileNotFoundError,
        "sheets",
        id="sheets",
    ),
]


def _new_client(client_cls, tmp_path: Path):
    kwargs = {
        "credentials_path": tmp_path / "credentials.json",
        "token_path": tmp_path / "token.json",
    }
    if client_cls is GmailClient:
        kwargs["mcp_token_path"] = tmp_path / "missing-mcp-token.json"
    if client_cls is GmailClient:
        with patch("core.integrations.gmail._require_google_api"):
            return client_cls(**kwargs)
    return client_cls(**kwargs)


def _clear_client_env(monkeypatch: pytest.MonkeyPatch, env_prefix: str | None) -> None:
    if env_prefix:
        monkeypatch.delenv(f"{env_prefix}_CLIENT_ID", raising=False)
        monkeypatch.delenv(f"{env_prefix}_CLIENT_SECRET", raising=False)


@pytest.mark.parametrize(("client_cls", "scopes", "env_prefix", "_error_cls", "_message"), _CLIENTS)
def test_loads_existing_token(client_cls, scopes, env_prefix, _error_cls, _message, tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "data"))
    _clear_client_env(monkeypatch, env_prefix)
    client = _new_client(client_cls, tmp_path)
    client.token_path.write_text("{}", encoding="utf-8")
    creds = MagicMock(valid=True)

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=creds) as load:
        assert client._get_credentials() is creds

    load.assert_called_once_with(str(client.token_path), scopes)


@pytest.mark.parametrize(("client_cls", "_scopes", "env_prefix", "_error_cls", "_message"), _CLIENTS)
def test_refreshes_expired_token(client_cls, _scopes, env_prefix, _error_cls, _message, tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "data"))
    _clear_client_env(monkeypatch, env_prefix)
    client = _new_client(client_cls, tmp_path)
    client.token_path.write_text("{}", encoding="utf-8")
    creds = MagicMock(valid=False, expired=True, refresh_token="refresh-token")
    creds.to_json.return_value = '{"token": "refreshed"}'

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=creds):
        assert client._get_credentials() is creds

    creds.refresh.assert_called_once()
    assert client.token_path.read_text(encoding="utf-8") == '{"token": "refreshed"}'


@pytest.mark.parametrize(("client_cls", "_scopes", "env_prefix", "error_cls", "message"), _CLIENTS)
def test_missing_token_preserves_integration_error(
    client_cls, _scopes, env_prefix, error_cls, message, tmp_path, monkeypatch
):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "data"))
    _clear_client_env(monkeypatch, env_prefix)
    client = _new_client(client_cls, tmp_path)
    expected = message
    if message == "calendar":
        expected = (
            f"No credentials found. Place credentials.json at {client.credentials_path} or set "
            "GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET environment variables."
        )
    elif message == "tasks":
        expected = (
            f"No credentials found. Place credentials.json at {client.credentials_path} or set "
            "GOOGLE_TASKS_CLIENT_ID and GOOGLE_TASKS_CLIENT_SECRET environment variables."
        )
    elif message == "sheets":
        expected = f"No credentials found. Place credentials.json and token.json at {client.credentials_path.parent}."

    with pytest.raises(error_cls, match=re.escape(expected)):
        client._get_credentials()


@pytest.mark.parametrize(("client_cls", "_scopes", "env_prefix", "_error_cls", "_message"), _CLIENTS[:1])
def test_gmail_prefers_mcp_token_to_saved_token(client_cls, _scopes, env_prefix, _error_cls, _message, tmp_path):
    client = _new_client(client_cls, tmp_path)
    client.mcp_token_path.write_text(
        json.dumps({"access_token": "mcp-access-token", "refresh_token": "mcp-refresh-token"}),
        encoding="utf-8",
    )
    client.token_path.write_text("{}", encoding="utf-8")

    creds = client._get_credentials()

    assert creds.token == "mcp-access-token"
    assert creds.refresh_token == "mcp-refresh-token"


@pytest.mark.parametrize(
    ("client_cls", "env_prefix"),
    [
        (GmailClient, "GMAIL"),
        (GoogleCalendarClient, "GOOGLE_CALENDAR"),
        (GoogleTasksClient, "GOOGLE_TASKS"),
    ],
)
def test_oauth_client_credentials_resolve_from_environment_only(client_cls, env_prefix, tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(f"{env_prefix}_CLIENT_ID", "env-client-id")
    monkeypatch.setenv(f"{env_prefix}_CLIENT_SECRET", "env-client-secret")
    kwargs = {
        "credentials_path": tmp_path / "credentials.json",
        "token_path": tmp_path / "token.json",
    }
    if client_cls is GmailClient:
        kwargs["mcp_token_path"] = tmp_path / "missing-mcp-token.json"
        with patch("core.integrations.gmail._require_google_api"):
            client = client_cls(**kwargs)
    else:
        client = client_cls(**kwargs)

    assert client.client_id == "env-client-id"
    assert client.client_secret == "env-client-secret"


def test_image_generation_credential_presence_uses_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FAL_KEY", "env-fal-key")

    from core.integrations.image_gen import _has_image_credential

    assert _has_image_credential("fal", "FAL_KEY")


def test_call_human_reads_configured_bot_token_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUSTOM_SLACK_TOKEN", "env-slack-token")

    from core.integrations.call_human import _get_bot_token

    assert _get_bot_token({"bot_token_env": "CUSTOM_SLACK_TOKEN"}) == "env-slack-token"
