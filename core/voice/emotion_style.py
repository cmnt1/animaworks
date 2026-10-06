from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Provider-specific emotion instructions shared by voice prompt builders."""

from typing import Literal

EmotionStyle = Literal["emoji", "audio_tags", "none"]
VoiceChannel = Literal["web", "phone"]


def emotion_style_for(provider: str | None) -> EmotionStyle:
    """Select the emotion syntax understood by a TTS provider."""
    normalized = (provider or "").strip().casefold()
    if normalized == "irodori":
        return "emoji"
    if normalized == "gemini":
        return "audio_tags"
    return "none"


_VOICE_FRONT_EMOJI_INSTRUCTION = (
    "- Always include emotion-conveying emojis in every reply; they are fed to the TTS engine and markedly improve "
    "its emotional accuracy. Use ONLY emojis the TTS understands as style cues: "
    "😊😆🫶😌🤭😏😎🤔😲😮😟😠🙄😪🥱😖😰😱😭🥺🫣🙏💪💥🥴 "
    "⏸️🐢⏩👂📢📖😮‍💨👌🤧. Others (😃😀😅❤️✨ etc.) garble the reading. "
    "One emoji barely registers — put 2-3 of the same emoji at the START of a short sentence to convey emotion.\n"
)
_VOICE_FRONT_AUDIO_TAG_INSTRUCTION = (
    "- Do not use emojis. When emotion needs to be conveyed, insert a sparingly used audio tag in the sentence, "
    "such as [giggles], [laughs], [sighs], [whispers], or [excited].\n"
)
_VOICE_FRONT_NO_EMOTION_MARKUP_INSTRUCTION = "- Do not use emojis or audio tags.\n"


def front_prompt_emotion_instruction(emotion_style: EmotionStyle) -> str:
    """Return the English voice-front rule for the selected emotion syntax."""
    if emotion_style == "emoji":
        return _VOICE_FRONT_EMOJI_INSTRUCTION
    if emotion_style == "audio_tags":
        return _VOICE_FRONT_AUDIO_TAG_INSTRUCTION
    return _VOICE_FRONT_NO_EMOTION_MARKUP_INSTRUCTION


_VOICE_MODE_PREFIX = "\n\n[voice-mode: 音声会話です。感情が伝わる話し言葉で200文字以内で簡潔に回答してください。"
_VOICE_MODE_EMOJI_INSTRUCTION = (
    "感情を表す絵文字を必ず入れてください（TTSの感情表現の精度が上がります）。"
    "絵文字はTTSが演技指示として解釈する次の中から選ぶこと: "
    "😊😆🫶😌🤭😏😎🤔😲😮😟😠🙄😪🥱😖😰😱😭🥺🫣🙏💪💥⏸️🐢⏩👂📢📖。"
    "これ以外（😃😀😅❤️✨等）は読みを乱すので使わない。"
    "感情を乗せたい短い文の先頭に同じ絵文字を2〜3個重ねると効果的です。"
)
_VOICE_MODE_AUDIO_TAG_INSTRUCTION = (
    "絵文字は使わず、感情表現が必要なときだけ [giggles] [laughs] [sighs] [whispers] [excited] "
    "などの音声タグを文中に入れてください。多用しないでください。"
)
_VOICE_MODE_NO_EMOTION_MARKUP_INSTRUCTION = "絵文字・音声タグは使わないでください。"
_VOICE_MODE_SUFFIX = (
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

_PHONE_MODE_PREFIX = (
    "\n\n[phone-mode: これは電話越しの音声認識結果です。誤認識があり得るため、意味が曖昧なら聞き返してください。"
    "電話で読み上げるので、話し言葉で150文字以内にしてください。Markdown・URLは使わないでください。"
    "英字の語は直後に全角括弧でカタカナの読みを付けてください。"
)
_PHONE_MODE_AUDIO_TAG_INSTRUCTION = (
    "絵文字は使わず、感情表現には [giggles] [laughs] [sighs] [whispers] [excited] などの音声タグを"
    "必要なときだけ文中に入れてください。多用しないでください。"
)
_PHONE_MODE_SUFFIX = (
    "時間のかかる依頼はその場で実行せず、自分宛てにタスクを作り、『タスクに積んでやっておきますね』と短く返してください。"
    "送金・削除・本番反映・外部への送信は、内容を復唱して『はい』と確認を取ってから着手してください。"
    "送金と削除は電話だけでは実行せず、Slackでの確認を求めてください。"
    '最後の行に既存どおり感情タグ <!-- emotion: {"emotion": "..."} --> を付けてもかまいません。]'
)


def _emotion_instruction(emotion_style: EmotionStyle, *, channel: VoiceChannel) -> str:
    if emotion_style == "emoji":
        return _VOICE_MODE_EMOJI_INSTRUCTION
    if emotion_style == "audio_tags":
        return _PHONE_MODE_AUDIO_TAG_INSTRUCTION if channel == "phone" else _VOICE_MODE_AUDIO_TAG_INSTRUCTION
    return _VOICE_MODE_NO_EMOTION_MARKUP_INSTRUCTION


def voice_mode_suffix(*, channel: VoiceChannel = "web", emotion_style: EmotionStyle = "emoji") -> str:
    """Build the Japanese voice-mode instruction for web or phone conversations."""
    instruction = _emotion_instruction(emotion_style, channel=channel)
    if channel == "phone":
        return _PHONE_MODE_PREFIX + instruction + _PHONE_MODE_SUFFIX
    return _VOICE_MODE_PREFIX + instruction + _VOICE_MODE_SUFFIX


__all__ = [
    "EmotionStyle",
    "VoiceChannel",
    "emotion_style_for",
    "front_prompt_emotion_instruction",
    "voice_mode_suffix",
]
