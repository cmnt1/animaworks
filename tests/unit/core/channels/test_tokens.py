"""Compatibility tests for per-Anima token resolution and credential precedence."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core.channels import tokens


def test_resolve_per_anima_token_uses_vault_before_shared_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookups: list[tuple[str, str]] = []

    def vault_lookup(key: str) -> str | None:
        lookups.append(("vault", key))
        return None

    def shared_lookup(key: str) -> str | None:
        lookups.append(("shared", key))
        return "discord-shared-token"

    monkeypatch.setattr(tokens, "_lookup_vault_credential", vault_lookup)
    monkeypatch.setattr(tokens, "_lookup_shared_credentials", shared_lookup)
    monkeypatch.setenv("DISCORD_BOT_TOKEN__mei", "discord-env-token")

    token = tokens.resolve_per_anima_token("discord", Path("/srv/animas/mei"), log=True)

    assert token == "discord-shared-token"
    assert lookups == [
        ("vault", "DISCORD_BOT_TOKEN__mei"),
        ("shared", "DISCORD_BOT_TOKEN__mei"),
    ]


def test_discord_per_anima_resolution_does_not_fall_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tokens, "_lookup_vault_credential", lambda _key: None)
    monkeypatch.setattr(tokens, "_lookup_shared_credentials", lambda _key: None)
    monkeypatch.setenv("DISCORD_BOT_TOKEN__mei", "discord-env-token")

    assert tokens.resolve_per_anima_token("discord", "mei") is None


def test_slack_per_anima_resolution_uses_environment_after_vault_and_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookups: list[str] = []
    monkeypatch.setattr(tokens, "_lookup_vault_credential", lambda key: lookups.append("vault") or None)
    monkeypatch.setattr(tokens, "_lookup_shared_credentials", lambda key: lookups.append("shared") or None)
    monkeypatch.setenv("SLACK_BOT_TOKEN__mei", "slack-env-token")

    token = tokens.resolve_per_anima_token("slack", "mei")

    assert token == "slack-env-token"
    assert lookups == ["vault", "shared"]


def test_per_anima_token_logging_preserves_service_message(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(tokens, "_lookup_vault_credential", lambda _key: "slack-vault-token")
    caplog.set_level(logging.DEBUG, logger="animaworks.tools")

    assert tokens.resolve_per_anima_token("slack", "mei", log=True) == "slack-vault-token"
    assert "Using per-Anima Slack token for 'mei'" in caplog.text


def test_call_human_preserves_custom_env_and_credentials_precedence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core.config.io import invalidate_cache
    from core.integrations.call_human import _get_bot_token

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(tmp_path / "animas" / "mei"))
    monkeypatch.setenv("SLACK_BOT_TOKEN", "shared-environment-token")
    monkeypatch.setenv("SLACK_BOT_TOKEN__mei", "per-anima-environment-token")
    monkeypatch.setenv("CALL_HUMAN_TOKEN", "channel-specific-environment-token")
    (tmp_path / "config.json").write_text(
        json.dumps({"credentials": {"slack": {"api_key": "config-credentials-token"}}}),
        encoding="utf-8",
    )
    invalidate_cache()
    try:
        # An explicit bot_token_env stays ahead of generic credential lookup.
        assert _get_bot_token({"bot_token_env": "CALL_HUMAN_TOKEN"}) == "channel-specific-environment-token"
        # The legacy call_human fallback ignores the per-Anima env key and
        # get_credential keeps config credentials ahead of the shared env.
        assert _get_bot_token({}) == "config-credentials-token"
    finally:
        invalidate_cache()
