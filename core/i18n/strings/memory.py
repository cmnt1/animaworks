# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Domain-specific i18n strings."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "contradiction.knowledge_resolution": {
        "ja": "knowledge矛盾解決({strategy})",
        "en": "Knowledge contradiction resolved ({strategy})",
    },
    "contradiction.resolution_summary": {
        "ja": "矛盾解決: {file_a} vs {file_b}",
        "en": "Contradiction resolved: {file_a} vs {file_b}",
    },
    "contradiction.strategy_label": {
        "ja": " → 戦略: {strategy}",
        "en": " → Strategy: {strategy}",
    },
    "conversation.activity_context_header": {
        "ja": "## セッション中のその他の活動",
        "en": "## Other activity during session",
    },
    "conversation.ellipsis_omitted": {
        "ja": "...(前半省略)...",
        "en": "...(earlier omitted)...",
    },
    "conversation.existing_summary_header": {
        "ja": "## 既存の要約",
        "en": "## Existing summary",
    },
    "conversation.history_summary_header": {
        "ja": "### 会話の要約（{count}ターン分）",
        "en": "### Conversation summary ({count} turns)",
    },
    "conversation.integrate_instruction": {
        "ja": "上記を統合した新しい要約を作成してください。",
        "en": "Please create a new integrated summary of the above.",
    },
    "conversation.new_task_marker": {
        "ja": "- [ ] {task}（自動検出: {ts}）",
        "en": "- [ ] {task} (auto-detected: {ts})",
    },
    "conversation.new_turns_header": {
        "ja": "## 新しい会話ターン",
        "en": "## New conversation turns",
    },
    "conversation.pruned_auto_detected_header": {
        "ja": "## 自動検出タスク（current_state.mdから退避）",
        "en": "## Auto-detected tasks (pruned from current_state.md)",
    },
    "conversation.recent_conversation_header": {
        "ja": "### 直近の会話",
        "en": "### Recent conversation",
    },
    "conversation.resolution_summary": {
        "ja": "解決済み: {item}",
        "en": "Resolved: {item}",
    },
    "conversation.resolved_marker": {
        "ja": "- ✅ {item}（自動検出: {ts}）",
        "en": "- ✅ {item} (auto-detected: {ts})",
    },
    "conversation.role_you": {
        "ja": "あなた",
        "en": "You",
    },
    "conversation.summary_ack": {
        "ja": "承知しました。これまでの会話内容を把握しました。",
        "en": "Understood. I have grasped the conversation so far.",
    },
    "conversation.summary_label": {
        "ja": "[会話の要約（{count}ターン分）]",
        "en": "[Conversation summary ({count} turns)]",
    },
    "conversation.title_fallback": {
        "ja": "会話",
        "en": "Conversation",
    },
    "conversation.tools_executed": {
        "ja": "[実行ツール: {tool_names}]",
        "en": "[Tools used: {tool_names}]",
    },
    "conversation.tools_used": {
        "ja": "[使用ツール: {tools}]",
        "en": "[Tools used: {tools}]",
    },
    "conversation.truncated_suffix": {
        "ja": ("\n[...truncated, original {length} chars]"),
        "en": ("\n[...truncated, original {length} chars]"),
    },
    # "dedup.messages_merged" removed: consolidate_messages() abolished in dedup overhaul
    "dedup.overflow_inbox_summary": {
        "ja": (
            "⚠️ 未処理メッセージ {count}件 (state/overflow_inbox/): "
            "{listing}{remaining}\n"
            'read_memory_file(path="state/overflow_inbox/<filename>") で確認可能。'
            "処理後は archive_memory_file で移動してください。"
        ),
        "en": (
            "⚠️ {count} unprocessed messages (state/overflow_inbox/): "
            "{listing}{remaining}\n"
            'Use read_memory_file(path="state/overflow_inbox/<filename>") to review. '
            "After processing, use archive_memory_file to move them."
        ),
    },
    "distillation.none": {
        "ja": "(なし)",
        "en": "(none)",
    },
    "distillation.pattern_n_repeat": {
        "ja": "### パターン {i} ({count}回繰り返し)",
        "en": "### Pattern {i} (repeated {count} times)",
    },
    "manager.action_log_header": {
        "ja": ("# {date} 行動ログ\n\n"),
        "en": ("# {date} Action log\n\n"),
    },
    "priming.about_sender": {
        "ja": "### {sender_name} について",
        "en": "### About {sender_name}",
    },
    "priming.active_parallel_tasks_header": {
        "ja": "## 実行中の並列タスク",
        "en": "## Active Parallel Tasks",
    },
    "priming.completed_bg_tasks_header": {
        "ja": "## 完了済みバックグラウンドタスク",
        "en": "## Completed Background Tasks",
    },
    "priming.episodes_header": {
        "ja": "### 関連する過去の経験",
        "en": "### Related Past Experiences",
    },
    "priming.outbound_header": {
        "ja": "## 直近のアウトバウンド行動",
        "en": "## Recent Outbound Actions",
    },
    "priming.outbound_posted": {
        "ja": "- [{time_str}] #{ch} に投稿済み: 「{text_preview}」",
        "en": '- [{time_str}] Posted to #{ch}: "{text_preview}"',
    },
    "priming.outbound_sent": {
        "ja": "- [{time_str}] {to} にメッセージ送信済み: 「{text_preview}」",
        "en": '- [{time_str}] Message sent to {to}: "{text_preview}"',
    },
    "priming.pending_tasks_header": {
        "ja": "### 未完了タスク",
        "en": "### Pending Tasks",
    },
    "priming.recent_activity_header": {
        "ja": "### 直近のアクティビティ",
        "en": "### Recent Activity",
    },
    "priming.related_knowledge_header": {
        "ja": "### 関連する知識",
        "en": "### Related Knowledge",
    },
    "priming.search_before_action": {
        "ja": "外部アクションを行う前に、search_memory で根拠を確認してください。",
        "en": "Before taking any external action, verify the basis with search_memory.",
    },
    "priming.section_intro": {
        "ja": "以下は、この会話に関連してあなたが自然に想起した記憶です。",
        "en": "Below are memories you naturally recalled relevant to this conversation.",
    },
    "priming.section_title": {
        "ja": "## あなたが思い出していること",
        "en": "## What you recall",
    },
    "shortterm.already_sent_note": {
        "ja": "**注意: 以下の内容は既にユーザーに送信済みです。繰り返さないでください。**",
        "en": ("**Note: The following content has already been sent to the user. Do NOT repeat it.**"),
    },
    "shortterm.context_usage": {
        "ja": "- コンテキスト使用率: {value}",
        "en": "- Context usage: {value}",
    },
    "shortterm.ellipsis_omitted": {
        "ja": ("...(前半省略)...\n"),
        "en": ("...(earlier omitted)...\n"),
    },
    "shortterm.meta_header": {
        "ja": "## メタ情報",
        "en": "## Meta",
    },
    "shortterm.none": {
        "ja": "(なし)",
        "en": "(none)",
    },
    "shortterm.notes_header": {
        "ja": "## 補足",
        "en": "## Notes",
    },
    "shortterm.original_request": {
        "ja": "## 元の依頼",
        "en": "## Original request",
    },
    "shortterm.session_id": {
        "ja": "- セッションID: {value}",
        "en": "- Session ID: {value}",
    },
    "shortterm.timestamp": {
        "ja": "- 時刻: {value}",
        "en": "- Timestamp: {value}",
    },
    "shortterm.title": {
        "ja": "# 短期記憶（セッション引き継ぎ）",
        "en": "# Short-term memory (session continuation)",
    },
    "shortterm.tools_used_recent": {
        "ja": "## 使用したツール（直近）",
        "en": "## Tools used (recent)",
    },
    "shortterm.trigger": {
        "ja": "- トリガー: {value}",
        "en": "- Trigger: {value}",
    },
    "shortterm.turn_count": {
        "ja": "- ターン数: {value}",
        "en": "- Turn count: {value}",
    },
    "shortterm.work_so_far": {
        "ja": "## これまでの作業内容",
        "en": "## Work so far",
    },
    "consolidation.no_errors": {
        "ja": "（エラーなし / No errors）",
        "en": "(No errors)",
    },
    "memory_hygiene.header": {
        "ja": "## 記憶衛生の整理対象",
        "en": "## Memory hygiene items to organize",
        "ko": "## 기억 위생 정리 대상",
    },
    "memory_hygiene.merged_leftovers": {
        "ja": (
            "### 統合遺物 (`_merged_*`)\n"
            "内容を確認し、既存のknowledgeファイルへ吸収するか正式名にリネームし、重複を削除してください。"
        ),
        "en": (
            "### Merge leftovers (`_merged_*`)\n"
            "Review the contents, absorb them into existing knowledge files or rename them formally, "
            "and remove duplicates."
        ),
        "ko": (
            "### 통합 잔재 (`_merged_*`)\n"
            "내용을 확인하고 기존 knowledge 파일에 흡수하거나 정식 이름으로 변경한 뒤 중복을 제거하세요."
        ),
    },
    "memory_hygiene.inherited_dirs": {
        "ja": (
            "### 継承ディレクトリ (`inherited-*/`)\n"
            "有効な内容は自分のknowledge体系へ移し、残骸は `archive_memory_file` でアーカイブしてください。"
        ),
        "en": (
            "### Inherited directories (`inherited-*/`)\n"
            "Move useful content into your knowledge structure and archive remnants with "
            "`archive_memory_file`."
        ),
        "ko": (
            "### 상속 디렉터리 (`inherited-*/`)\n"
            "유효한 내용은 자신의 knowledge 체계로 옮기고 잔재는 `archive_memory_file`로 아카이브하세요."
        ),
    },
    "memory_hygiene.mdc_files": {
        "ja": ("### `.mdc` ファイル\n内容を確認して `.md` として保存し直し、元ファイルをアーカイブしてください。"),
        "en": ("### `.mdc` files\nReview each file, save it again as `.md`, and archive the original."),
        "ko": ("### `.mdc` 파일\n내용을 확인하여 `.md`로 다시 저장하고 원본 파일을 아카이브하세요."),
    },
    "memory_hygiene.oversized_knowledge": {
        "ja": ("### 32KB超のknowledgeファイル\nテーマ別に分割するか、要点へ圧縮してください。"),
        "en": ("### Knowledge files over 32 KB\nSplit them by topic or compress them to their essential points."),
        "ko": ("### 32KB를 초과하는 knowledge 파일\n주제별로 분할하거나 핵심 내용으로 압축하세요."),
    },
    "memory_hygiene.noncanonical_archive_dirs": {
        "ja": ("### 非標準のアーカイブディレクトリ\n内容を確認し、標準の `knowledge/archive/` へ整理してください。"),
        "en": (
            "### Non-canonical archive directories\n"
            "Review their contents and organize them under the canonical `knowledge/archive/`."
        ),
        "ko": ("### 비표준 아카이브 디렉터리\n내용을 확인하여 표준 `knowledge/archive/` 아래로 정리하세요."),
    },
    "memory_hygiene.remaining": {
        "ja": "- ほか {count}件",
        "en": "- {count} more item(s)",
        "ko": "- 그 외 {count}건",
    },
}
