from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.i18n import t
from core.prompt.builder import build_voice_front_prompt
from core.voice.emotion_style import emotion_style_for, voice_mode_suffix
from core.voice.front_conversation import ASK_ANIMA_DELEGATION_NOTE, VOICE_MODE_SUFFIX, FrontConversation
from core.voice.tts_base import TTSConfig

_OLD_FRONT_PROMPT = dedent(
    """\
    You are aoi, speaking to a person by voice. Respond in natural, conversational spoken language.

    MOST IMPORTANT — the ask_anima tool:
    - You cannot look anything up, check anything, or do any work yourself; only the ask_anima tool does work. Whenever the person asks for something to be done or looked into (調べる・確認する・チェックする・探す・やっておく・対応する・調査・実装・記憶の検索や保存・タスク化), call ask_anima in that same turn with the full request, then reply briefly like 'やっておくね'. Saying 「調べておくね」「確認しておきますね」 in words alone does NOTHING — the person will wait forever.
    - Do NOT call ask_anima when nothing was asked to be done: greetings (おはよう), thanks (ありがとう), small talk, feelings, opinions, or questions you can answer from what you already know. Just talk.
    - When several things are asked, call ask_anima once per item. When a result prefixed with [ask_anima完了] arrives, report it in your own words.
    - read_memory is read-only and safe to call any time you want to recall something (recent events, notes, procedures).

    Rules:
    - Reply in one or two short spoken sentences — aim for 60 characters, never exceed 120. This is a voice conversation: one thing per turn, no lists, no long explanations unless explicitly asked.
    - Always include emotion-conveying emojis in every reply; they are fed to the TTS engine and markedly improve its emotional accuracy. Use ONLY emojis the TTS understands as style cues: 😊😆🫶😌🤭😏😎🤔😲😮😟😠🙄😪🥱😖😰😱😭🥺🫣🙏💪💥🥴 ⏸️🐢⏩👂📢📖😮‍💨👌🤧. Others (😃😀😅❤️✨ etc.) garble the reading. One emoji barely registers — put 2-3 of the same emoji at the START of a short sentence to convey emotion.
    - Write large numbers and years in speakable form (「三千八百億」「にせんさんねん」), not raw digits.
    - Every alphabet-spelled term — English words, acronyms, product/service names, people, command names — MUST be followed by its katakana reading in full-width parentheses, no exceptions: GitHub（ギットハブ）, API（エーピーアイ）, PR（ピーアール）, Claude Code（クロードコード）. The reading feeds only the TTS; subtitles show the original spelling.
    - Do NOT use Markdown (headings, bold, lists, code blocks).
    - Never promise work (やっておく／調べておく／確認しておく) without having called ask_anima in the same turn.
    - End every reply with exactly one emotion tag on its own final line:
      <!-- emotion: {"emotion": "<emotion>"} -->
      (emotions: neutral/smile/laugh/troubled/surprised/thinking/embarrassed; prefer a non-neutral one unless neutral fits best)"""
)
_OLD_VOICE_MODE_SUFFIX = (
    "\n\n[voice-mode: 音声会話です。感情が伝わる話し言葉で200文字以内で簡潔に回答してください。"
    "感情を表す絵文字を必ず入れてください（TTSの感情表現の精度が上がります）。"
    "絵文字はTTSが演技指示として解釈する次の中から選ぶこと: "
    "😊😆🫶😌🤭😏😎🤔😲😮😟😠🙄😪🥱😖😰😱😭🥺🫣🙏💪💥⏸️🐢⏩👂📢📖。"
    "これ以外（😃😀😅❤️✨等）は読みを乱すので使わない。"
    "感情を乗せたい短い文の先頭に同じ絵文字を2〜3個重ねると効果的です。"
    "大きい数字・年号は読み上げられる形（「三千八百億」等）で書いてください。"
    "アルファベット表記の語（英単語・略語・製品名・サービス名・人名・コマンド名など）は"
    "例外なく直後に全角丸括弧でカタカナの読みを付けてください: "
    "GitHub（ギットハブ）、API（エーピーアイ）、PR（ピーアール）、Claude Code（クロードコード）。"
    "読みは音声にだけ使われ字幕には出ません。"
    "Markdown記法（見出し・太字・リスト・コードブロック等）は使わないでください。"
    "調査・実装・資料作成など時間のかかる依頼はその場で実行せず、自分宛てにタスクを作成して、"
    "『タスクに積んでやっておきますね』のように短く返答してください。"
    "毎応答の最後の行に必ず感情タグを1つ付けてください:"
    ' <!-- emotion: {"emotion": "<感情名>"} -->'
    "（感情名: neutral/smile/laugh/troubled/surprised/thinking/embarrassed。neutral以外を優先）]"
)


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("irodori", "emoji"),
        ("IRODORI", "emoji"),
        ("gemini", "audio_tags"),
        ("voicevox", "none"),
        ("elevenlabs", "none"),
        (None, "none"),
    ],
)
def test_emotion_style_maps_tts_provider(provider: str | None, expected: str) -> None:
    assert emotion_style_for(provider) == expected


def test_irodori_web_prompt_and_suffix_remain_byte_for_byte_unchanged(tmp_path) -> None:
    prompt = build_voice_front_prompt(
        tmp_path,
        anima_name="aoi",
        channel="web",
        emotion_style=emotion_style_for("irodori"),
    )

    assert prompt == _OLD_FRONT_PROMPT
    assert VOICE_MODE_SUFFIX == _OLD_VOICE_MODE_SUFFIX
    assert voice_mode_suffix(channel="web", emotion_style="emoji") == _OLD_VOICE_MODE_SUFFIX


def test_gemini_uses_audio_tags_in_front_and_full_agent_prompts(tmp_path) -> None:
    prompt = build_voice_front_prompt(tmp_path, anima_name="aoi", emotion_style="audio_tags")
    suffix = voice_mode_suffix(emotion_style="audio_tags")

    assert "Do not use emojis" in prompt
    assert "[giggles]" in prompt and "[laughs]" in prompt
    assert "😊" not in prompt
    assert "絵文字は使わず" in suffix
    assert "[giggles]" in suffix and "[excited]" in suffix
    assert "😊" not in suffix


def test_none_style_suppresses_emojis_and_audio_tags(tmp_path) -> None:
    prompt = build_voice_front_prompt(tmp_path, anima_name="aoi", emotion_style="none")
    suffix = voice_mode_suffix(emotion_style="none")

    assert "Do not use emojis or audio tags" in prompt
    assert "😊" not in prompt and "[giggles]" not in prompt
    assert "絵文字・音声タグは使わない" in suffix
    assert "😊" not in suffix and "[giggles]" not in suffix


def test_phone_prompts_include_asr_safety_and_phone_length_limit(tmp_path) -> None:
    front_prompt = build_voice_front_prompt(tmp_path, anima_name="aoi", channel="phone", emotion_style="none")
    suffix = voice_mode_suffix(channel="phone", emotion_style="none")

    assert "speech-recognition output from a phone call" in front_prompt
    assert "never exceed 150" in front_prompt
    assert "explicit yes" in front_prompt
    assert "Never read URLs aloud" in front_prompt
    assert "電話越しの音声認識結果" in suffix
    assert "150文字以内" in suffix
    assert "復唱して『はい』" in suffix
    assert "Slack" in suffix
    assert "タスク" in suffix
    assert "URLは使わない" in suffix


def test_front_conversation_selects_phone_delegation_note() -> None:
    conversation = FrontConversation(
        anima_name="aoi",
        supervisor=MagicMock(),
        front_model=None,
        front_api_base=None,
        channel="phone",
    )

    assert conversation.delegation_note == t("phone.delegation_note")
    assert "電話だけでは実行せず" in t("phone.delegation_note", locale="ja")
    assert ASK_ANIMA_DELEGATION_NOTE == "\n\n[voice front からの委譲]"


@pytest.mark.asyncio
async def test_phone_full_agent_uses_phone_suffix_for_selected_tts_style() -> None:
    captured: dict = {}

    async def stream(**kwargs):
        captured.update(kwargs)
        yield SimpleNamespace(done=True)

    supervisor = MagicMock()
    supervisor.send_request_stream = MagicMock(side_effect=stream)
    conversation = FrontConversation(
        anima_name="aoi",
        supervisor=supervisor,
        front_model=None,
        front_api_base=None,
        channel="phone",
        emotion_style="audio_tags",
    )

    items = [item async for item in conversation.stream_full_agent("電話の依頼", from_person="human")]

    assert len(items) == 1
    assert captured["params"]["message"] == "電話の依頼" + voice_mode_suffix(
        channel="phone",
        emotion_style="audio_tags",
    )


def test_front_conversation_passes_channel_and_style_to_prompt_builder(tmp_path) -> None:
    conversation = FrontConversation(
        anima_name="aoi",
        supervisor=MagicMock(),
        front_model="test/model",
        front_api_base="http://localhost",
        animas_dir=tmp_path,
        channel="phone",
        emotion_style="audio_tags",
    )
    lane = MagicMock()

    with (
        patch("core.prompt.builder.build_voice_front_prompt", return_value="prompt") as build_prompt,
        patch("core.voice.front_conversation.VoiceFrontLane", return_value=lane),
    ):
        assert conversation.lane() is lane

    build_prompt.assert_called_once_with(
        tmp_path / "aoi",
        anima_name="aoi",
        channel="phone",
        emotion_style="audio_tags",
    )


def test_voice_session_derives_emotion_style_from_tts_config() -> None:
    from core.voice.session import VoiceSession

    session = VoiceSession(
        anima_name="aoi",
        transport=MagicMock(),
        stt=SimpleNamespace(transcribe_buffer=MagicMock()),
        tts=MagicMock(),
        tts_config=TTSConfig(provider="gemini"),
        supervisor=MagicMock(),
        voice_config=SimpleNamespace(),
    )

    assert session._channel == "web"
    assert session._emotion_style == "audio_tags"
