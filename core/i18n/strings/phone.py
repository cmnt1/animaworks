from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Phone-channel prompts and spoken phrases."""

STRINGS: dict[str, dict[str, str]] = {
    "phone.mode_suffix": {
        "ja": (
            "\n\n[phone-mode: これは電話越しの音声認識結果です。誤認識があり得るため、意味が曖昧なら聞き返してください。"
            "電話で読み上げるので、話し言葉で150文字以内にしてください。Markdown・絵文字・URLは使わないでください。"
            "英字の語は直後に全角括弧でカタカナの読みを付けてください。"
            "感情表現には [giggles] [laughs] [sighs] [whispers] [excited] などの音声タグを使ってもかまいませんが、多用しないでください。"
            "時間のかかる依頼はその場で実行せず、自分宛てにタスクを作り、『タスクに積んでやっておきますね』と短く返してください。"
            "送金・削除・本番反映・外部への送信は、内容を復唱して『はい』と確認を取ってから着手してください。"
            "送金と削除は電話だけでは実行せず、Slackでの確認を求めてください。"
            '最後の行に既存どおり感情タグ <!-- emotion: {"emotion": "..."} --> を付けてもかまいません。]'
        ),
        "en": (
            "\n\n[phone-mode: This is speech-recognition output from a phone call and may contain errors. Ask for clarification when the meaning is ambiguous. "
            "Reply conversationally in 150 characters or fewer because the answer will be read aloud. Do not use Markdown, emoji, or URLs. "
            "For English words or acronyms in a Japanese reply, immediately add the katakana pronunciation in full-width parentheses. "
            "You may use Gemini TTS tags such as [giggles], [laughs], [sighs], [whispers], and [excited] sparingly. "
            "Do not perform time-consuming work during the call; create a task for yourself and briefly say you will add it to your task list. "
            "Before acting on money transfers, deletions, production changes, or external messages, repeat the action and get an explicit yes. "
            "Never perform transfers or deletions based only on a phone call; ask for confirmation in Slack. "
            'You may append the usual final emotion tag: <!-- emotion: {"emotion": "..."} -->.]'
        ),
    },
    "phone.link_placeholder": {
        "ja": "リンク",
        "en": "link",
    },
    "phone.delegation_note": {
        "ja": (
            "\n\n[電話の前さばきからの委譲] taka が電話で頼んだ内容（音声認識の結果）。"
            "送金と削除は電話だけでは実行せず、Slack で taka に確認を取る。"
            "結果は電話で読み上げるので要点を短く返す。"
        ),
        "en": (
            "\n\n[Delegated from the phone voice front] This is taka's phone request (speech-recognition output). "
            "Do not make transfers or deletions based only on the call; confirm with taka in Slack. "
            "The result will be read aloud, so keep the summary brief."
        ),
    },
    "phone.pin_prompt": {
        "ja": "暗証番号を入力してください。",
        "en": "Please enter your PIN.",
    },
    "phone.pin_invalid": {
        "ja": "暗証番号が違います。もう一度入力してください。",
        "en": "That PIN is incorrect. Please try again.",
    },
    "phone.pin_locked": {
        "ja": "認証に失敗しました。電話を終了します。",
        "en": "Authentication failed. This call will now end.",
    },
    "phone.greeting": {
        "ja": "認証しました。何でも話してください。",
        "en": "You are authenticated. What would you like to talk about?",
    },
    "phone.voice_filler_1": {
        "ja": "うん、",
        "en": "Mm-hmm,",
        "ko": "응,",
    },
    "phone.voice_filler_2": {
        "ja": "えっとね、",
        "en": "Let me think,",
        "ko": "음,",
    },
    "phone.voice_filler_3": {
        "ja": "なるほど、",
        "en": "I see,",
        "ko": "그렇구나,",
    },
    "phone.alert_choice": {
        "ja": "確認したら1を、{anima}と話したいことがあれば2を押してください。",
        "en": "Press 1 to acknowledge this alert, or press 2 to speak with {anima}.",
    },
    "phone.alert_ack": {
        "ja": "確認しました。電話を切ります。",
        "en": "The alert is acknowledged. Goodbye.",
    },
    "phone.alert_invalid_choice": {
        "ja": "1か2を押してください。",
        "en": "Please press 1 or 2.",
    },
    "phone.alert_intro": {
        "ja": "{anima}です。緊急のお知らせです。{subject}。{body}",
        "en": "This is {anima} with an urgent alert. {subject}. {body}",
    },
    "phone.wait": {
        "ja": "少々お待ちください。",
        "en": "Please wait a moment.",
    },
    "phone.still_thinking": {
        "ja": "まだ考えています。もう少しお待ちください。",
        "en": "I am still thinking. Please wait a little longer.",
    },
    "phone.turn_timeout": {
        "ja": "時間がかかっているので、終わったらSlackで報告します。",
        "en": "This is taking longer than expected. I will report back in Slack when it is done.",
    },
    "phone.silence_retry": {
        "ja": "すみません、聞き取れませんでした。もう一度話してください。",
        "en": "Sorry, I did not catch that. Please say it again.",
    },
    "phone.goodbye": {
        "ja": "また何かあれば電話してね。",
        "en": "Call me again whenever you need anything.",
    },
    "phone.turn_error": {
        "ja": "ごめんなさい、うまく答えられませんでした。",
        "en": "Sorry, I could not prepare an answer this time.",
    },
    "phone.delegation_report_subject": {
        "ja": "電話で頼まれた件の結果（{anima}）",
        "en": "Results of the phone request ({anima})",
    },
    "phone.delegation_still_running": {
        "ja": "[ask_anima job {job}: 30分以内に完了を確認できませんでした。依頼: {request}]",
        "en": "[ask_anima job {job}: still running after 30 minutes. Request: {request}]",
    },
}
