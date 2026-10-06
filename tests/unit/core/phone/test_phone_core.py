from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config.models import PhoneConfig
from core.phone.audio_store import AudioStore
from core.phone.session import PhoneSessionStore
from core.phone.speech import clean_for_speech
from core.phone.twilio_client import TwilioAPIError, TwilioClient, validate_signature
from core.voice.tts_base import TTSConfig
from core.voice.voice_config import load_per_anima_voice


def _signature(secret: str, url: str, params: dict[str, str]) -> str:
    payload = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def test_twilio_signature_accepts_known_hmac_sha1_vector() -> None:
    secret = "phone-test-auth-token"
    url = "https://phone.example.test/api/webhooks/twilio/voice?alert=alert-123"
    params = {"CallSid": "CA0001", "Digits": "2", "From": "+15551234567"}
    signature = _signature(secret, url, params)

    assert validate_signature(secret, url, params, signature) is True


def test_twilio_signature_rejects_tampering_and_wrong_public_url() -> None:
    secret = "phone-test-auth-token"
    url = "https://phone.example.test/api/webhooks/twilio/voice"
    params = {"CallSid": "CA0001", "Direction": "inbound"}
    signature = _signature(secret, url, params)

    assert validate_signature(secret, url, {**params, "Direction": "outbound-api"}, signature) is False
    assert validate_signature(secret, url + "?alert=other", params, signature) is False
    assert validate_signature(secret, url, params, "") is False
    assert validate_signature(secret, url, params, "☃") is False
    assert validate_signature("", url, params, signature) is False


def test_twilio_signature_sorts_multi_value_parameters() -> None:
    secret = "multi-value-secret"
    url = "https://phone.example.test/webhook"
    params = {"Tag": ["z", "a"]}
    expected = _signature(secret, url, {"Tag": "a"})
    payload = url + "Tag" + "a" + "Tag" + "z"
    actual = base64.b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha1).digest()).decode()

    assert validate_signature(secret, url, params, actual)
    assert actual != expected


@pytest.mark.asyncio
async def test_twilio_client_creates_call_without_exposing_credentials() -> None:
    response = MagicMock(status_code=201)
    response.json.return_value = {"sid": "CA123", "status": "queued"}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.post.return_value = response

    with patch("core.phone.twilio_client.httpx.AsyncClient", return_value=client):
        result = await TwilioClient("AC123", "never-print-this-token").create_call(
            to="+15551234567",
            from_="+15557654321",
            url="https://phone.example.test/voice",
            status_callback="https://phone.example.test/status",
        )

    assert result["sid"] == "CA123"
    args, kwargs = client.post.await_args
    assert args[0].endswith("/Accounts/AC123/Calls.json")
    assert kwargs["data"]["Url"] == "https://phone.example.test/voice"
    assert kwargs["data"]["StatusCallback"] == "https://phone.example.test/status"
    assert "never-print-this-token" not in repr(kwargs["data"])


@pytest.mark.asyncio
async def test_twilio_client_returns_safe_error_for_failed_request() -> None:
    response = MagicMock(status_code=401)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    client.post.return_value = response

    with (
        patch("core.phone.twilio_client.httpx.AsyncClient", return_value=client),
        pytest.raises(TwilioAPIError) as exc_info,
    ):
        await TwilioClient("AC123", "secret-token").create_call(
            to="+15551234567",
            from_="+15557654321",
            url="https://phone.example.test/voice",
            status_callback="https://phone.example.test/status",
        )

    assert "secret-token" not in str(exc_info.value)
    assert "HTTP 401" in str(exc_info.value)


def test_audio_store_expires_and_evicts_least_recent_item() -> None:
    now = [10.0]
    store = AudioStore(ttl_seconds=5, max_items=2, clock=lambda: now[0])
    first = store.put(b"first")
    second = store.put(b"second")
    assert store.get(first) == b"first"  # make first most recently used
    third = store.put(b"third")

    assert store.get(second) is None
    assert store.get(first) == b"first"
    assert store.get(third) == b"third"
    now[0] = 15.0
    assert store.get(first) is None
    assert len(store) == 0


def test_audio_store_requires_nonempty_audio() -> None:
    store = AudioStore()
    with pytest.raises(ValueError, match="must not be empty"):
        store.put(b"")


def test_phone_session_store_tracks_and_discards_call_state() -> None:
    sessions = PhoneSessionStore()
    session = sessions.create("CA123", "aoi", kind="alert", alert_id="alert-1")

    assert session.kind == "alert"
    assert session.alert_id == "alert-1"
    assert sessions.create("CA123", "other") is session
    assert sessions.get("CA123") is session
    assert sessions.discard("CA123") is session
    assert sessions.get("CA123") is None


def test_speech_cleanup_removes_markdown_and_replaces_links() -> None:
    text = "## Status\n\n- **Ready**: [the docs](https://example.com/help)\nUse https://example.org now."

    spoken = clean_for_speech(text)

    assert spoken == "Status\nReady: the docs、リンク\nUse リンク now."
    assert "**" not in spoken
    assert "https://" not in spoken


def test_speech_cleanup_caps_text_at_400_characters() -> None:
    spoken = clean_for_speech("x" * 500)

    assert len(spoken) == 400
    assert spoken.endswith("…")


def test_existing_voice_helper_resolves_per_anima_tts_config(tmp_path) -> None:
    animas_dir = tmp_path / "animas"
    status_path = animas_dir / "aoi" / "status.json"
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        json.dumps({"voice": {"tts_provider": "gemini", "voice_id": "Aoede", "speed": 1.2, "pitch": -0.2}}),
        encoding="utf-8",
    )
    global_voice = SimpleNamespace(default_tts_provider="voicevox")

    config = load_per_anima_voice(animas_dir, "aoi", global_voice)

    assert config == TTSConfig(provider="gemini", voice_id="Aoede", speed=1.2, pitch=-0.2)


def test_existing_voice_helper_uses_global_provider_when_status_is_missing(tmp_path) -> None:
    config = load_per_anima_voice(tmp_path / "animas", "aoi", SimpleNamespace(default_tts_provider="gemini"))

    assert config.provider == "gemini"
    assert config.voice_id == ""
    assert config.speed == 1.0


@pytest.mark.asyncio
async def test_speech_synthesis_uses_voice_factory_and_caches_fixed_phrase(tmp_path, monkeypatch) -> None:
    from core.phone import speech

    status_path = tmp_path / "animas" / "aoi" / "status.json"
    status_path.parent.mkdir(parents=True)
    status_path.write_text(json.dumps({"voice": {"tts_provider": "gemini", "voice_id": "Aoede"}}), encoding="utf-8")
    voice_config = SimpleNamespace(default_tts_provider="voicevox")
    provider = SimpleNamespace(synthesize_full=AsyncMock(return_value=b"wav-bytes"))
    factory = MagicMock(return_value=provider)
    monkeypatch.setattr(speech, "create_tts_provider", factory)
    speech.clear_static_audio_cache()

    first = await speech.synthesize_speech(
        "aoi",
        "**Please wait**",
        animas_dir=tmp_path / "animas",
        voice_config=voice_config,
        cache_key="ja:wait",
    )
    second = await speech.synthesize_speech(
        "aoi",
        "**Please wait**",
        animas_dir=tmp_path / "animas",
        voice_config=voice_config,
        cache_key="ja:wait",
    )

    assert first == second == b"wav-bytes"
    factory.assert_called_once_with("gemini", voice_config)
    provider.synthesize_full.assert_awaited_once_with("Please wait", TTSConfig(provider="gemini", voice_id="Aoede"))
    speech.clear_static_audio_cache()


def test_phone_prompts_have_japanese_and_english_translations() -> None:
    from core.i18n import t

    assert "曖昧" in t("phone.mode_suffix", locale="ja")
    assert "speech-recognition" in t("phone.mode_suffix", locale="en")
    assert t("phone.wait", locale="ja") == "少々お待ちください。"
    assert t("phone.wait", locale="en") == "Please wait a moment."


def test_phone_config_is_available_in_core_type() -> None:
    assert PhoneConfig().enabled is False
