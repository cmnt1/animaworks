from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.i18n import t
from core.voice.speech_text import prepare_speech
from core.voice.tts_base import TTSConfig


def test_display_keeps_original_ruby_term_while_spoken_uses_reading() -> None:
    speech = prepare_speech("GitHub（ギットハブ）で確認します。", provider="voicevox")

    assert speech.display == "GitHubで確認します。"
    assert speech.spoken == "ギットハブで確認します。"


def test_irodori_keeps_only_supported_emojis_and_applies_reading_rules(tmp_path, monkeypatch) -> None:
    import core.voice.speech_text as speech_text

    (tmp_path / "voice_yomi.tsv").write_text("小鳥遊\tたかなし\n", encoding="utf-8")
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(speech_text, "_yomi_cache", None)
    monkeypatch.setattr(speech_text, "_yomi_mtime", 0.0)

    speech = prepare_speech("😊😃小鳥遊さんは2003年、API（エーピーアイ）です。", provider="irodori")

    assert speech.display == "😊小鳥遊さんは2003年、APIです。"
    assert speech.spoken == "😊たかなしさんはにせんさんねん、エーピーアイです。"


def test_irodori_resolves_ruby_and_kansuji_years() -> None:
    speech = prepare_speech("2026年です。二〇二六年も同じです。", provider="irodori")

    assert speech.display == "2026年です。二〇二六年も同じです。"
    assert speech.spoken == "にせんにじゅうろくねんです。にせんにじゅうろくねんも同じです。"


def test_non_irodori_does_not_apply_yomi_or_year_conversion(tmp_path, monkeypatch) -> None:
    import core.voice.speech_text as speech_text

    (tmp_path / "voice_yomi.tsv").write_text("小鳥遊\tたかなし\n", encoding="utf-8")
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(speech_text, "_yomi_cache", None)
    monkeypatch.setattr(speech_text, "_yomi_mtime", 0.0)

    speech = prepare_speech("小鳥遊さんのRAG 2003年。", provider="voicevox")

    assert speech.display == "小鳥遊さんのRAG 2003年。"
    assert speech.spoken == "小鳥遊さんのRAG 2003年。"


def test_audio_tags_are_not_removed_from_gemini_speech() -> None:
    speech = prepare_speech("[laughs] うれしい😊です。", provider="gemini")

    assert speech.display == "[laughs] うれしいです。"
    assert speech.spoken == "[laughs] うれしいです。"


def test_url_and_markdown_link_are_replaced_with_phone_placeholder() -> None:
    speech = prepare_speech(
        "[the docs](https://example.com/help) and https://example.org now.",
        provider="voicevox",
        link_placeholder="リンク",
    )

    assert speech.display == "the docs、リンク and リンク now."
    assert speech.spoken == speech.display
    assert "https://" not in speech.spoken


def test_truncation_caps_spoken_text_and_adds_ellipsis() -> None:
    speech = prepare_speech("x" * 500, provider="voicevox", max_chars=400)

    assert len(speech.display) == 400
    assert len(speech.spoken) == 400
    assert speech.spoken.endswith("…")


def test_phone_truncation_happens_after_url_replacement() -> None:
    speech = prepare_speech(
        "https://example.com/" + "x" * 410,
        provider="voicevox",
        link_placeholder="リンク",
        max_chars=20,
    )

    assert speech.spoken == "リンク"


def test_markdown_and_emotion_metadata_are_removed() -> None:
    speech = prepare_speech(
        '## Status\n\n- **Ready** `now`\n<!-- emotion: {"emotion": "smile"} -->',
        provider="voicevox",
    )

    assert speech.display == "Status\nReady now"
    assert speech.spoken == "Status\nReady now"
    assert "**" not in speech.spoken
    assert "<!--" not in speech.spoken


def test_empty_speech_and_invalid_limit() -> None:
    assert prepare_speech("😊", provider="voicevox").spoken == ""
    with pytest.raises(ValueError, match="must be positive"):
        prepare_speech("text", provider="voicevox", max_chars=0)


@pytest.mark.asyncio
async def test_phone_emergency_alert_synthesis_uses_prepared_spoken_text(tmp_path, monkeypatch) -> None:
    from core.phone import speech as phone_speech

    alert_text = t(
        "phone.alert_intro",
        locale="ja",
        anima="aoi",
        subject="Disk",
        body="障害の詳細 https://example.com/incident",
    )
    tts_config = TTSConfig(provider="gemini", voice_id="Aoede")
    voice_config = SimpleNamespace(default_tts_provider="voicevox")
    provider = SimpleNamespace(synthesize_full=AsyncMock(return_value=b"wav-bytes"))
    factory = MagicMock(return_value=provider)
    original_prepare = phone_speech.prepare_speech
    prepare_calls: list[dict[str, object]] = []

    def recording_prepare(text: str, **kwargs):
        prepare_calls.append({"text": text, **kwargs})
        return original_prepare(text, **kwargs)

    monkeypatch.setattr(phone_speech, "load_per_anima_voice", lambda *_args: tts_config)
    monkeypatch.setattr(phone_speech, "create_tts_provider", factory)
    monkeypatch.setattr(phone_speech, "prepare_speech", recording_prepare)
    phone_speech.clear_static_audio_cache()

    audio = await phone_speech.synthesize_speech(
        "aoi",
        alert_text,
        animas_dir=tmp_path,
        voice_config=voice_config,
        link_placeholder="リンク",
        max_chars=400,
    )

    assert audio == b"wav-bytes"
    assert prepare_calls == [{"text": alert_text, "provider": "gemini", "link_placeholder": "リンク", "max_chars": 400}]
    spoken = provider.synthesize_full.await_args.args[0]
    assert "https://" not in spoken
    assert "リンク" in spoken
    assert len(spoken) <= 400
    phone_speech.clear_static_audio_cache()
