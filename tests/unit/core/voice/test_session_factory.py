from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.voice.session_factory import build_voice_session
from core.voice.tts_base import TTSConfig


def test_build_voice_session_resolves_shared_settings_for_phone(tmp_path: Path) -> None:
    voice_config = SimpleNamespace(proactive_enabled=True)
    stt = MagicMock()
    tts = MagicMock()
    tts_config = TTSConfig(provider="gemini", voice_id="Aoede")
    tts_factory = MagicMock(return_value=tts)
    human_notifications = SimpleNamespace(enabled=True)

    session = build_voice_session(
        anima_name="aoi",
        transport=MagicMock(),
        stt=stt,
        supervisor=MagicMock(),
        animas_dir=tmp_path,
        voice_config=voice_config,
        channel="phone",
        from_person="taka",
        thread_id="twilio-phone",
        proactive_enabled=False,
        human_notification_config=human_notifications,
        report_delegations_on_close=True,
        tts_factory=tts_factory,
        tts_config_loader=lambda *_args: tts_config,
        front_settings_loader=lambda *_args: ("front/model", "http://front.test/v1"),
    )

    tts_factory.assert_called_once_with("gemini", voice_config)
    assert session._stt is stt
    assert session._tts is tts
    assert session._emotion_style == "audio_tags"
    assert session._channel == "phone"
    assert session._from_person == "taka"
    assert session._front_conversation.thread_id == "twilio-phone"
    assert session._front_conversation.front_model == "front/model"
    assert session._front_conversation.front_api_base == "http://front.test/v1"
    assert session._front_conversation.animas_dir == tmp_path
    assert session._proactive_enabled is False
    assert session._human_notification_config is human_notifications
    assert session._report_delegations_on_close is True


def test_build_voice_session_uses_web_disconnect_setting_by_default(tmp_path: Path) -> None:
    voice_config = SimpleNamespace(
        proactive_enabled=True,
        notify_delegations_on_web_disconnect=True,
    )

    session = build_voice_session(
        anima_name="aoi",
        transport=MagicMock(),
        stt=MagicMock(),
        supervisor=MagicMock(),
        animas_dir=tmp_path,
        voice_config=voice_config,
        tts_factory=lambda *_args: MagicMock(),
        tts_config_loader=lambda *_args: TTSConfig(provider="voicevox"),
        front_settings_loader=lambda *_args: (None, None),
    )

    assert session._channel == "web"
    assert session._proactive_enabled is True
    assert session._report_delegations_on_close is True
