from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.routes.phone as phone_routes
from core.config.models import AnimaWorksConfig, PhoneConfig
from core.phone.audio_store import phone_audio_store
from core.phone.session import phone_sessions

_TEST_AUTH_TOKEN = "test-twilio-token-not-a-real-secret"
_PUBLIC_BASE_URL = "https://phone.example.test"
_VOICE_PATH = "/api/webhooks/twilio/voice"


class _FakeSupervisor:
    def __init__(self, response: str = '電話での回答です <!-- emotion: {"emotion": "smile"} -->') -> None:
        self.response = response
        self.calls: list[dict] = []

    async def send_request_stream(self, *, anima_name: str, method: str, params: dict, timeout: float):
        self.calls.append({"anima_name": anima_name, "method": method, "params": params, "timeout": timeout})
        yield SimpleNamespace(
            done=False,
            chunk=json.dumps({"type": "text_delta", "text": self.response}),
            result=None,
        )
        yield SimpleNamespace(done=True, chunk=None, result={"response": self.response})


@pytest.fixture
def phone_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    config = AnimaWorksConfig(
        phone=PhoneConfig(
            enabled=True,
            anima="aoi",
            public_base_url=_PUBLIC_BASE_URL,
            owner_numbers=["+15551234567"],
            from_number="+15557654321",
            thread_id="phone",
            turn_timeout_sec=30,
        )
    )
    app = FastAPI()
    app.include_router(phone_routes.create_phone_router(), prefix="/api")
    app.state.animas_dir = tmp_path / "animas"
    app.state.supervisor = _FakeSupervisor()

    monkeypatch.setattr(phone_routes, "load_config", lambda: config)
    monkeypatch.setattr(phone_routes, "get_twilio_credentials", lambda _config: ("AC123", _TEST_AUTH_TOKEN))
    monkeypatch.setattr(
        phone_routes,
        "get_vault_manager",
        lambda: SimpleNamespace(get=lambda _section, _key: "1234"),
    )

    async def fake_speech(_anima: str, _text: str, **_kwargs) -> bytes:
        return b"RIFF-test-wav"

    monkeypatch.setattr(phone_routes, "synthesize_speech", fake_speech)
    phone_sessions.clear()
    phone_audio_store.clear()
    yield app, config
    phone_sessions.clear()
    phone_audio_store.clear()


def _twilio_signature(url: str, form: dict[str, str]) -> str:
    payload = url + "".join(key + form[key] for key in sorted(form))
    digest = hmac.new(_TEST_AUTH_TOKEN.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _signed_post(
    client: TestClient,
    path: str,
    form: dict[str, str],
    *,
    query: str = "",
    signature: str | None = None,
) -> object:
    target = f"{path}?{query}" if query else path
    public_url = f"{_PUBLIC_BASE_URL}{target}"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if signature is None:
        headers["X-Twilio-Signature"] = _twilio_signature(public_url, form)
    else:
        headers["X-Twilio-Signature"] = signature
    return client.post(target, content=urlencode(form), headers=headers)


def _make_phone_audio_response_token(response_text: str) -> str:
    root = ElementTree.fromstring(response_text)
    play = root.find("Play")
    assert play is not None and play.text
    return urlsplit(play.text).path.rsplit("/", 1)[-1].removesuffix(".wav")


def test_phone_post_requires_twilio_signature(phone_app) -> None:
    app, _config = phone_app
    with TestClient(app) as client:
        missing = client.post(_VOICE_PATH, data={"CallSid": "CA1", "Direction": "inbound"})
        invalid = _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA1", "Direction": "inbound"},
            signature="not-a-valid-signature",
        )

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_disabled_phone_endpoints_return_404(phone_app, monkeypatch: pytest.MonkeyPatch) -> None:
    app, config = phone_app
    config.phone.enabled = False
    with TestClient(app) as client:
        webhook = client.post(_VOICE_PATH, data={"CallSid": "CA1"})
        audio = client.get("/api/webhooks/twilio/audio/unknown.wav")

    assert webhook.status_code == 404
    assert audio.status_code == 404


def test_unregistered_inbound_number_is_rejected(phone_app) -> None:
    app, _config = phone_app
    with TestClient(app) as client:
        response = _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA-UNREGISTERED", "Direction": "inbound", "From": "+15550000000"},
        )

    assert response.status_code == 200
    assert "<Reject/>" in response.text
    assert phone_sessions.get("CA-UNREGISTERED") is None


def test_registered_caller_can_pin_speak_and_receive_anima_response(phone_app) -> None:
    app, _config = phone_app
    supervisor = _FakeSupervisor()
    app.state.supervisor = supervisor
    speech_inputs: list[str] = []

    async def record_speech(_anima: str, text: str, **_kwargs) -> bytes:
        speech_inputs.append(text)
        return b"RIFF-test-wav"

    phone_routes.synthesize_speech = record_speech
    with TestClient(app) as client:
        incoming = _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA-VOICE-1", "Direction": "inbound", "From": "+15551234567"},
        )
        pin = _signed_post(
            client,
            "/api/webhooks/twilio/pin",
            {"CallSid": "CA-VOICE-1", "Digits": "1234"},
        )
        turn = _signed_post(
            client,
            "/api/webhooks/twilio/turn",
            {"CallSid": "CA-VOICE-1", "SpeechResult": "今日の予定を教えて"},
        )
        poll = _signed_post(
            client,
            "/api/webhooks/twilio/poll",
            {"CallSid": "CA-VOICE-1"},
        )
        token = _make_phone_audio_response_token(poll.text)
        audio = client.get(f"/api/webhooks/twilio/audio/{token}.wav")
        missing_audio = client.get("/api/webhooks/twilio/audio/unknown-token.wav")

    assert incoming.status_code == 200 and 'input="dtmf"' in incoming.text
    assert pin.status_code == 200 and 'input="speech"' in pin.text and 'language="ja-JP"' in pin.text
    assert turn.status_code == 200 and "<Redirect" in turn.text and "/poll" in turn.text
    assert poll.status_code == 200 and "<Play>" in poll.text and 'input="speech"' in poll.text
    assert audio.status_code == 200 and audio.content == b"RIFF-test-wav"
    assert audio.headers["content-type"].startswith("audio/wav")
    assert missing_audio.status_code == 404

    assert len(supervisor.calls) == 1
    request = supervisor.calls[0]
    assert request["anima_name"] == "aoi"
    assert request["method"] == "process_message"
    assert request["params"]["voice_mode"] is True
    assert request["params"]["thread_id"] == "phone"
    assert "[phone-mode:" in request["params"]["message"]
    assert "今日の予定を教えて" in request["params"]["message"]
    assert request["params"]["from_person"] == "human"
    assert request["params"]["images"] == []
    assert request["params"]["attachment_paths"] == []
    assert "電話での回答です" in speech_inputs
    assert "<!-- emotion:" not in speech_inputs[-1]


def test_pin_failures_hang_up_after_three_attempts(phone_app) -> None:
    app, _config = phone_app
    with TestClient(app) as client:
        _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA-PIN-FAIL", "Direction": "inbound", "From": "+15551234567"},
        )
        first = _signed_post(client, "/api/webhooks/twilio/pin", {"CallSid": "CA-PIN-FAIL", "Digits": "１２３４"})
        second = _signed_post(client, "/api/webhooks/twilio/pin", {"CallSid": "CA-PIN-FAIL", "Digits": "9999"})
        third = _signed_post(client, "/api/webhooks/twilio/pin", {"CallSid": "CA-PIN-FAIL", "Digits": "1111"})

    assert first.status_code == second.status_code == third.status_code == 200
    assert "<Gather" in first.text and "<Gather" in second.text
    assert "<Hangup/>" in third.text
    assert "1234" not in first.text + second.text + third.text


def test_turn_hangs_up_before_pin_authentication(phone_app) -> None:
    app, _config = phone_app
    phone_sessions.create("CA-UNAUTH", "aoi")
    with TestClient(app) as client:
        response = _signed_post(
            client,
            "/api/webhooks/twilio/turn",
            {"CallSid": "CA-UNAUTH", "SpeechResult": "秘密を教えて"},
        )

    assert response.status_code == 200
    assert "<Hangup/>" in response.text
    assert not app.state.supervisor.calls


def test_alert_call_plays_audio_and_digit_one_acknowledges(phone_app, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _config = phone_app
    token = phone_audio_store.put(b"RIFF-alert-wav")
    alert = SimpleNamespace(alert_id="alert-1", anima="aoi", audio_token=token)
    acknowledged: list[str] = []
    monkeypatch.setattr(phone_routes, "get_alert", lambda _alert_id: alert)
    monkeypatch.setattr(phone_routes, "acknowledge_alert", acknowledged.append)

    with TestClient(app) as client:
        started = _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA-ALERT-1", "Direction": "outbound-api"},
            query="alert=alert-1",
        )
        choice = _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA-ALERT-1", "Digits": "1"},
            query="alert=alert-1&phase=choice",
        )

    assert started.status_code == 200
    assert "<Play>https://phone.example.test/api/webhooks/twilio/audio/" in started.text
    assert 'input="dtmf"' in started.text and "&amp;phase=choice" in started.text
    assert choice.status_code == 200 and "<Hangup/>" in choice.text
    assert acknowledged == ["alert-1"]


def test_alert_silence_replays_alert_once_and_hangs_up(phone_app, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _config = phone_app
    token = phone_audio_store.put(b"RIFF-alert-wav")
    alert = SimpleNamespace(alert_id="alert-2", anima="aoi", audio_token=token)
    monkeypatch.setattr(phone_routes, "get_alert", lambda _alert_id: alert)

    with TestClient(app) as client:
        _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA-ALERT-2", "Direction": "outbound-api"},
            query="alert=alert-2",
        )
        no_input = _signed_post(
            client,
            _VOICE_PATH,
            {"CallSid": "CA-ALERT-2", "Digits": ""},
            query="alert=alert-2&phase=choice",
        )

    assert no_input.status_code == 200
    assert no_input.text.count("<Play>") == 1
    assert "<Hangup/>" in no_input.text
    assert phone_sessions.get("CA-ALERT-2").acknowledged is False


def test_status_callback_discards_completed_call_session(phone_app) -> None:
    app, _config = phone_app
    phone_sessions.create("CA-DONE", "aoi")

    with TestClient(app) as client:
        response = _signed_post(
            client,
            "/api/webhooks/twilio/status",
            {"CallSid": "CA-DONE", "CallStatus": "completed"},
        )

    assert response.status_code == 204
    assert phone_sessions.get("CA-DONE") is None
