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
            "あなたの最終回答テキストはDiscordの送信元（スレッド含む）に自動投稿されます。"
            "discord_channel_post / discord send / send_message / TaskExec等での返信は一切不要です。"
            "send_messageで送信者に返信するとDMチャネルに届いてしまい、スレッドには届きません。"
            "テキストで回答を書くだけで自動的に届きます。"
            "【重要】スレッド内の話題を親チャンネルや他チャンネルにpost_channelで転載しないでください。"
            "スレッドの内容はスレッド内で完結させてください"
        ),
        "en": (
            "Your final text response will be auto-posted to the originating Discord channel/thread. "
            "Do NOT use discord_channel_post, discord send, send_message, TaskExec, or any other method. "
            "Using send_message will deliver to a DM channel, NOT the thread. "
            "Just write your response as text — it will be delivered automatically. "
            "IMPORTANT: Do NOT repost thread content to the parent channel or other channels via post_channel. "
            "Keep thread discussions within the thread"
        ),
    },
    "discord.thread_post_channel_warning": {
        "ja": (
            "⚠ このメッセージはDiscordスレッド内の話題です。"
            "スレッドへの返信はAutoResponderが自動投稿します。"
            "post_channelでボードに投稿すると親チャンネルにも転送されます。"
            "本当にボードへの投稿が必要ですか？"
        ),
        "en": (
            "⚠ This message originated from a Discord thread. "
            "Thread replies are auto-posted by AutoResponder. "
            "Using post_channel will broadcast to the parent channel. "
            "Are you sure you need to post to the board?"
        ),
    },
}
