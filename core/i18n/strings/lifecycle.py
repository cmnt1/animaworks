# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Domain-specific i18n strings."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "cascade.activity_read_failed": {
        "ja": "GlobalOutboundLimitExceeded: アクティビティログ読み取り失敗のため送信をブロックしました",
        "en": ("GlobalOutboundLimitExceeded: Sending blocked because the activity log could not be read"),
    },
    "cascade.daily_limit": {
        "ja": (
            "GlobalOutboundLimitExceeded: 24時間あたりの送信上限（{max_per_day}通）に到達しています（現在{daily_count}通/24h）。 このターンではsend_messageを使わず、送信内容をcurrent_state.mdに記録して次のセッションで送信してください。"
        ),
        "en": (
            "GlobalOutboundLimitExceeded: Daily send limit ({max_per_day} messages) reached ({daily_count} msgs/24h). Do not use send_message this turn. Record the message content in current_state.md and send it in the next session."
        ),
    },
    "cascade.hourly_limit": {
        "ja": (
            "GlobalOutboundLimitExceeded: 1時間あたりの送信上限（{max_per_hour}通）に到達しています（現在{hourly_count}通/1h, {daily_count}通/24h）。{reset_at} このターンではsend_messageを使わず、送信内容をcurrent_state.mdに記録して次のセッションで送信してください。"
        ),
        "en": (
            "GlobalOutboundLimitExceeded: Hourly send limit ({max_per_hour} messages) reached ({hourly_count} msgs/1h, {daily_count} msgs/24h).{reset_at} Do not use send_message this turn. Record the message content in current_state.md and send it in the next session."
        ),
    },
    "cascade.hourly_reset_at": {
        "ja": " 次の送信可能時刻（目安）: {reset_time}",
        "en": " Estimated next send time: {reset_time}",
    },
    "heartbeat.history_plan_entry": {
        "ja": "- {ts}: [計画] {plan}",
        "en": "- {ts}: [Plan] {plan}",
    },
    "heartbeat.current_state_cleanup_required": {
        "ja": (
            "【要整理】current_state.md が {current_chars} 文字あり、上限 {max_chars} 文字に近づいています。"
            "本題に入る前に current_state.md を自分で整理してください: "
            "(1) 完了・解決済み・期限切れの項目を削除する（経緯はepisodesに自動記録済みなので消してよい）、"
            "(2) 継続中の案件は1件につき見出し1行＋要点数行に圧縮する、"
            "(3) cronの実行記録・同期カーソル・定期チェックの「差分なし」報告は current_state.md ではなく "
            "state/ 配下の専用ファイル（例: state/<タスク名>-cursor.md）に移す。"
            "整理後は {target_chars} 文字以内を目安とする。"
            "放置すると上限超過時にシステムが古い方から機械的に切り捨てるため、重要な項目が失われる恐れがあります。"
        ),
        "en": (
            "[Cleanup required] Your current_state.md is {current_chars} chars, approaching the {max_chars}-char limit. "
            "Before the main task, reorganize current_state.md yourself: "
            "(1) delete completed/resolved/expired items (their history is already auto-recorded in episodes), "
            "(2) compress each ongoing item to one heading plus a few key lines, "
            "(3) move cron run records, sync cursors, and no-diff check reports out of current_state.md "
            "into dedicated files under state/ (e.g. state/<task>-cursor.md). "
            "Aim for {target_chars} chars or less after cleanup. "
            "If left as is, the system will mechanically drop the oldest content once the limit is exceeded, "
            "and important items may be lost."
        ),
    },
    "scheduler.cron_fallback_description": {
        "ja": "cron.mdの「{task_name}」の指示に従って処理してください。",
        "en": "Follow the instructions for '{task_name}' in cron.md.",
    },
    "governor.supervisor_notify": {
        "ja": "[Governor] {anima} をクォータ超過により一時停止しました。理由: {reason}",
        "en": "[Governor] {anima} has been suspended due to quota limit. Reason: {reason}",
    },
    "governor.human_notify": {
        "ja": "Governor: {anima} がクォータ超過で停止されました。理由: {reason}",
        "en": "Governor: {anima} suspended due to quota. Reason: {reason}",
    },
    "governor.human_notify_subject": {
        "ja": "Governor アラート",
        "en": "Governor Alert",
    },
}
