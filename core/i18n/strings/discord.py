from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Discord integration i18n strings."""

STRINGS: dict[str, dict[str, str]] = {
    "discord.annotation_mentioned": {
        "ja": "あなたがメンションされています",
        "en": "you are mentioned",
    },
    "discord.annotation_no_mention": {
        "ja": "あなたへの直接メンションはありません",
        "en": "no direct mention for you",
    },
    "discord.auto_reply_instruction": {
        "ja": (
            "あなたの最終回答テキストはDiscordに自動投稿されます。"
            "discord_channel_post / discord send / TaskExec等での送信は一切不要です。"
            "テキストで回答を書くだけで自動的に届きます"
        ),
        "en": (
            "Your final text response will be auto-posted to Discord. "
            "Do NOT use discord_channel_post, discord send, TaskExec, or any other method to send it. "
            "Just write your response as text — it will be delivered automatically"
        ),
    },
}
