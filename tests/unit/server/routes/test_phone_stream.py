from __future__ import annotations

import base64
import io
import json
import time
import wave
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server.routes.phone_stream as phone_stream
from core.config.models import AnimaWorksConfig, PhoneConfig, VoiceConfig
from core.phone.session import phone_sessions
from core.phone.stream_tokens import PhoneStreamTokenStore
from core.voice.audio_codec import pcm16_to_mulaw
from core.voice.session import VoiceSession
from core.voice.tts_base import TTSConfig
from core.voice.turn_detector import TurnDetector


@pytest.fixture
def stream_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    config = AnimaWorksConfig(
        phone=PhoneConfig(
            enabled=True,
            anima="aoi",
            public_base_url="https://phone.example.test",
            from_person="taka",
            thread_id="phone",
        ),
        voice=VoiceConfig(),
    )
    app = FastAPI()
    from server.routes.phone import create_phone_router

    app.include_router(create_phone_router(), prefix="/api")
    app.state.supervisor = object()
    app.state.animas_dir = tmp_path / "animas"
    monkeypatch.setattr(phone_stream, "load_config", lambda: config)
    monkeypatch.setattr(phone_stream, "_get_stt", lambda _config: object())
    phone_sessions.clear()
    phone_stream.phone_stream_tokens.clear()
    yield app, config
    phone_sessions.clear()
    phone_stream.phone_stream_tokens.clear()


def _wav(duration_ms: int = 20) -> bytes:
    pcm = np.full(24_000 * duration_ms // 1000, 1_000, dtype="<i2").tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24_000)
        wav_file.writeframes(pcm)
    return output.getvalue()


def _start(token: str, call_sid: str = "CA-STREAM") -> dict:
    return {
        "event": "start",
        "start": {
            "streamSid": "MZ-STREAM",
            "callSid": call_sid,
            "customParameters": {"token": token},
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
        },
    }


def _media_packet(*, speech: bool) -> str:
    samples = np.full(160, 8_000 if speech else 0, dtype="<i2").tobytes()
    payload = base64.b64encode(pcm16_to_mulaw(samples)).decode("ascii")
    return json.dumps({"event": "media", "media": {"payload": payload}})


class _FakeVoiceSession:
    def __init__(self, transport) -> None:
        self.transport = transport
        self.speech_ends: list[str] = []
        self.audio_bytes = 0
        self.probes = 0
        self.closed = False

    async def speak_text(self, text: str) -> bool:
        self.greeting = text
        await self.transport.send_audio(_wav())
        return True

    async def handle_audio_chunk(self, data: bytes) -> None:
        self.audio_bytes += len(data)

    async def handle_speech_end(self, from_person: str = "human") -> None:
        self.speech_ends.append(from_person)
        await self.transport.send_audio(_wav())

    async def handle_barge_probe(self) -> None:
        self.probes += 1

    async def handle_discard_audio(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


def _install_fake_session(monkeypatch: pytest.MonkeyPatch) -> tuple[list[_FakeVoiceSession], list[dict]]:
    sessions: list[_FakeVoiceSession] = []
    options: list[dict] = []

    def build(**kwargs):
        options.append(kwargs)
        session = _FakeVoiceSession(kwargs["transport"])
        sessions.append(session)
        return session

    monkeypatch.setattr(phone_stream, "build_voice_session", build)
    return sessions, options


def test_media_stream_start_media_reaches_speech_end_and_returns_media_mark(stream_app, monkeypatch) -> None:
    app, config = stream_app
    sessions, options = _install_fake_session(monkeypatch)
    detector_instances: list[TurnDetector] = []
    detector_redemptions: list[int] = []
    detector_time = [0.0]
    config.phone.turn_end_silence_ms = 2300

    def detector_factory(*, redemption_ms: int):
        detector = TurnDetector(
            lambda frame: 0.9 if np.max(np.abs(np.frombuffer(frame, dtype="<i2"))) > 500 else 0.0,
            clock=lambda: detector_time[0],
            redemption_ms=redemption_ms,
        )
        detector_instances.append(detector)
        detector_redemptions.append(redemption_ms)
        return detector

    monkeypatch.setattr(phone_stream, "TurnDetector", detector_factory)
    phone_sessions.create("CA-STREAM", "aoi").authenticated = True
    token = phone_stream.phone_stream_tokens.issue("CA-STREAM")

    with TestClient(app) as client, client.websocket_connect("/api/webhooks/twilio/stream") as websocket:
        websocket.send_text(json.dumps({"event": "connected"}))
        websocket.send_text(json.dumps(_start(token)))
        greeting_media = websocket.receive_json()
        greeting_mark = websocket.receive_json()
        assert greeting_media["event"] == "media"
        assert greeting_mark["event"] == "mark"
        websocket.send_text(
            json.dumps(
                {
                    "event": "mark",
                    "streamSid": "MZ-STREAM",
                    "mark": greeting_mark["mark"],
                }
            )
        )
        deadline = time.monotonic() + 1.0
        while detector_instances[0].is_playback_active and time.monotonic() < deadline:
            time.sleep(0.005)
        assert detector_instances[0].is_playback_active is False
        detector_time[0] = 2.0

        voice = _media_packet(speech=True)
        silence = _media_packet(speech=False)
        for _ in range(30):
            websocket.send_text(voice)
        for _ in range(125):
            websocket.send_text(silence)

        response_messages = []
        while len(response_messages) < 4:
            message = websocket.receive_json()
            response_messages.append(message)
            if message.get("event") == "mark" and message["mark"]["name"] != greeting_mark["mark"]["name"]:
                websocket.send_text(json.dumps({"event": "mark", "mark": message["mark"], "streamSid": "MZ-STREAM"}))
                break
        websocket.send_text(json.dumps({"event": "stop"}))

    assert detector_redemptions == [2300]
    assert detector_instances[0]._redemption_ms == 2300
    assert sessions[0].greeting
    assert sessions[0].speech_ends == ["taka"]
    assert sessions[0].audio_bytes > 0
    assert sessions[0].closed is True
    assert options[0]["channel"] == "phone"
    assert options[0]["from_person"] == "taka"
    assert options[0]["thread_id"] == "phone"
    assert options[0]["proactive_enabled"] is False
    assert options[0]["report_delegations_on_close"] is True
    response_events = [message["event"] for message in response_messages]
    assert "media" in response_events and "mark" in response_events
    assert detector_instances[0].is_playback_active is False


def test_invalid_token_is_rejected_on_start(stream_app, monkeypatch) -> None:
    app, _config = stream_app
    _install_fake_session(monkeypatch)
    phone_sessions.create("CA-STREAM", "aoi").authenticated = True

    with TestClient(app) as client, client.websocket_connect("/api/webhooks/twilio/stream") as websocket:
        websocket.send_text(json.dumps(_start("not-a-token")))
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()


def test_expired_token_is_rejected_on_start(stream_app, monkeypatch) -> None:
    app, _config = stream_app
    _install_fake_session(monkeypatch)
    now = [0.0]
    token_store = PhoneStreamTokenStore(ttl_seconds=1, clock=lambda: now[0])
    monkeypatch.setattr(phone_stream, "phone_stream_tokens", token_store)
    token = token_store.issue("CA-STREAM")
    now[0] = 1.0
    phone_sessions.create("CA-STREAM", "aoi").authenticated = True

    with TestClient(app) as client, client.websocket_connect("/api/webhooks/twilio/stream") as websocket:
        websocket.send_text(json.dumps(_start(token)))
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()


def test_reused_token_is_rejected_after_first_connection(stream_app, monkeypatch) -> None:
    app, _config = stream_app
    sessions, _options = _install_fake_session(monkeypatch)
    phone_sessions.create("CA-STREAM", "aoi").authenticated = True
    token = phone_stream.phone_stream_tokens.issue("CA-STREAM")

    with TestClient(app) as client:
        with client.websocket_connect("/api/webhooks/twilio/stream") as websocket:
            websocket.send_text(json.dumps(_start(token)))
            websocket.send_text(json.dumps({"event": "stop"}))
        assert sessions[0].closed is True
        with client.websocket_connect("/api/webhooks/twilio/stream") as websocket:
            websocket.send_text(json.dumps(_start(token)))
            with pytest.raises(WebSocketDisconnect):
                websocket.receive_text()


def test_phone_disabled_rejects_websocket_before_accept(stream_app) -> None:
    app, config = stream_app
    config.phone.enabled = False

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/api/webhooks/twilio/stream"),
    ):
        pass


def test_optional_twilio_signature_is_checked_for_public_wss_url(stream_app, monkeypatch) -> None:
    app, _config = stream_app
    sessions, _options = _install_fake_session(monkeypatch)
    monkeypatch.setattr(phone_stream, "get_twilio_credentials", lambda _phone: ("AC", "secret"))
    phone_sessions.create("CA-STREAM", "aoi").authenticated = True

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/api/webhooks/twilio/stream",
            headers={"X-Twilio-Signature": "invalid"},
        ),
    ):
        pass

    assert sessions == []


def test_unstarted_stream_cannot_send_media(stream_app) -> None:
    app, _config = stream_app
    with TestClient(app) as client, client.websocket_connect("/api/webhooks/twilio/stream") as websocket:
        websocket.send_text(_media_packet(speech=True))
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_text()


def test_stream_drives_real_voice_session_with_mocked_stt_and_tts(stream_app, monkeypatch) -> None:
    app, config = stream_app

    class MockSTT:
        calls = 0

        def transcribe_buffer(self, _audio: bytes, initial_prompt: str = "") -> dict:
            self.calls += 1
            return {"raw_text": "明日の予定を教えて", "language": "ja", "segments": []}

        async def transcribe_buffer_async(self, _audio: bytes) -> dict:
            self.calls += 1
            return {"raw_text": "明日の予定を教えて", "language": "ja"}

    class MockTTS:
        async def health_check(self) -> bool:
            return True

        async def synthesize(self, _text: str, _tts_config: TTSConfig):
            yield _wav()

    class MockSupervisor:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def send_request_stream(self, *, anima_name: str, method: str, params: dict, timeout: float):
            self.calls.append({"anima_name": anima_name, "method": method, "params": params, "timeout": timeout})
            yield SimpleNamespace(
                done=False,
                chunk=json.dumps({"type": "text_delta", "text": "電話の回答です。"}),
                result=None,
            )
            yield SimpleNamespace(done=True, chunk=None, result={"cycle_result": {"emotion": "smile"}})

    stt = MockSTT()
    supervisor = MockSupervisor()
    app.state.supervisor = supervisor
    monkeypatch.setattr(phone_stream, "_get_stt", lambda _config: stt)

    def build(**kwargs):
        return VoiceSession(
            anima_name=kwargs["anima_name"],
            transport=kwargs["transport"],
            stt=kwargs["stt"],
            tts=MockTTS(),
            tts_config=TTSConfig(provider="voicevox"),
            supervisor=kwargs["supervisor"],
            voice_config=kwargs["voice_config"],
            channel=kwargs["channel"],
            from_person=kwargs["from_person"],
            thread_id=kwargs["thread_id"],
            proactive_enabled=kwargs["proactive_enabled"],
            human_notification_config=kwargs["human_notification_config"],
            report_delegations_on_close=kwargs["report_delegations_on_close"],
        )

    monkeypatch.setattr(phone_stream, "build_voice_session", build)
    clock = [0.0]
    detectors: list[TurnDetector] = []

    def detector_factory(*, redemption_ms: int) -> TurnDetector:
        detector = TurnDetector(
            lambda frame: 0.9 if np.max(np.abs(np.frombuffer(frame, dtype="<i2"))) > 500 else 0.0,
            clock=lambda: clock[0],
            redemption_ms=redemption_ms,
        )
        detectors.append(detector)
        return detector

    monkeypatch.setattr(phone_stream, "TurnDetector", detector_factory)
    phone_sessions.create("CA-STREAM", "aoi").authenticated = True
    token = phone_stream.phone_stream_tokens.issue("CA-STREAM")

    with TestClient(app) as client, client.websocket_connect("/api/webhooks/twilio/stream") as websocket:
        websocket.send_text(json.dumps(_start(token)))
        greeting_media = websocket.receive_json()
        greeting_mark = websocket.receive_json()
        assert greeting_media["event"] == "media"
        assert greeting_mark["event"] == "mark"
        websocket.send_text(json.dumps({"event": "mark", "mark": greeting_mark["mark"]}))
        greeting_media_2 = websocket.receive_json()
        greeting_mark_2 = websocket.receive_json()
        assert greeting_media_2["event"] == "media"
        assert greeting_mark_2["event"] == "mark"
        websocket.send_text(json.dumps({"event": "mark", "mark": greeting_mark_2["mark"]}))
        deadline = time.monotonic() + 1.0
        while detectors[0].is_playback_active and time.monotonic() < deadline:
            time.sleep(0.005)
        assert detectors[0].is_playback_active is False
        clock[0] = 2.0

        voice = _media_packet(speech=True)
        silence = _media_packet(speech=False)
        for _ in range(30):
            websocket.send_text(voice)
        for _ in range(110):
            websocket.send_text(silence)

        response_messages = []
        while len(response_messages) < 6:
            message = websocket.receive_json()
            response_messages.append(message)
            if message.get("event") == "mark" and message["mark"]["name"] != greeting_mark["mark"]["name"]:
                websocket.send_text(json.dumps({"event": "mark", "mark": message["mark"]}))
                break
        websocket.send_text(json.dumps({"event": "stop"}))

    assert stt.calls > 0
    assert len(supervisor.calls) == 1
    request = supervisor.calls[0]
    assert request["anima_name"] == "aoi"
    assert request["params"]["thread_id"] == config.phone.thread_id
    assert request["params"]["from_person"] == config.phone.from_person
    assert "明日の予定を教えて" in request["params"]["message"]
    assert "[phone-mode:" in request["params"]["message"]
    assert "media" in [message["event"] for message in response_messages]
    assert "mark" in [message["event"] for message in response_messages]
