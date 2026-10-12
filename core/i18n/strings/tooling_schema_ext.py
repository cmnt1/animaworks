# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Domain-specific i18n strings (schema.* part 2)."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "schema.task_tracker.desc": {
        "ja": (
            "delegate_task で委譲したタスクの進捗を追跡する。自分のタスクキューから delegated ステータスのエントリを取得し、部下側の最新ステータスと突き合わせて返す。"
        ),
        "en": (
            "Track progress of tasks delegated via delegate_task. Retrieves delegated-status entries from your task queue and cross-references them with the subordinate's latest status."
        ),
    },
    "schema.task_tracker.status": {
        "ja": "フィルタ（all: 全件, active: 進行中, completed: 完了済み）。デフォルト: active",
        "en": ("Filter (all: all tasks, active: in-progress, completed: finished). Default: active"),
    },
    "schema.update_task.desc": {
        "ja": ("タスクのステータスを更新する。完了時は status='done'、中断時は status='cancelled' に設定する。"),
        "en": ("Update a task's status. Set status='done' on completion, status='cancelled' on abort."),
        "ko": ("작업 상태를 업데이트한다. 완료 시 status='done', 중단 시 status='cancelled'로 설정한다."),
    },
    "schema.update_task.status": {
        "ja": "新しいステータス",
        "en": "New status",
    },
    "schema.update_task.resume": {
        "ja": "保存済みの依頼文をそのまま使い、同じ task_id で実行待ちに戻す。status='pending' と一緒に指定する。",
        "en": "Requeue the task under the same task_id using its saved request, unchanged. Specify together with status='pending'.",
    },
    "schema.update_task.summary": {
        "ja": "更新後の要約（任意）",
        "en": "Updated summary (optional)",
        "ko": "업데이트 후 요약(선택 사항)",
    },
    "schema.update_task.result": {
        "ja": "完了時の成果要約（任意）",
        "en": "Completion result summary (optional)",
        "ko": "완료 결과 요약(선택 사항)",
    },
    "schema.update_task.task_id": {
        "ja": "タスクID（backlog_task時に返されたID）",
        "en": "Task ID (the ID returned by backlog_task)",
    },
    "schema.vault_get.desc": {
        "ja": (
            "暗号化されたクレデンシャルvaultから値を取得する。自分の名前空間とsharedのみ読み取り可能。section省略時は自分の名前空間、次にsharedを検索する。"
        ),
        "en": (
            "Retrieve a value from the encrypted credential vault. Only your own namespace and shared are readable. If section is omitted, your namespace is searched before shared."
        ),
    },
    "schema.vault_get.key": {
        "ja": "キー名（例: 'api_key', 'master_password'）",
        "en": "Key name (e.g. 'api_key', 'master_password')",
    },
    "schema.vault_get.section": {
        "ja": "自分の名前空間またはshared（省略時は両方を検索）",
        "en": "Your own namespace or shared (omit to search both)",
    },
    "schema.vault_list.desc": {
        "ja": "自分の名前空間とsharedにあるキー名だけを一覧表示する。他のAnimaの名前空間は表示されず、値も表示されない。",
        "en": ("List key names in your own namespace and shared. Other Animas' namespaces and all values are hidden."),
    },
    "schema.vault_list.section": {
        "ja": "自分の名前空間またはshared（省略時は両方を一覧表示）",
        "en": "Your own namespace or shared (omit to list both)",
    },
    "schema.vault_store.desc": {
        "ja": "自分の名前空間に値を暗号化して保存する。sharedや他のAnimaの名前空間には書き込めない。",
        "en": (
            "Encrypt and store a value in your own namespace. Animas cannot write to shared or another Anima's namespace."
        ),
    },
    "schema.vault_store.key": {
        "ja": "キー名（例: 'api_key', 'master_password'）",
        "en": "Key name (e.g. 'api_key', 'master_password')",
    },
    "schema.vault_store.section": {
        "ja": "自分の名前空間（省略時は自動選択）",
        "en": "Your own namespace (selected automatically when omitted)",
    },
    "schema.vault_store.value": {
        "ja": "保存する値（暗号化されて保存される）",
        "en": "Value to store (will be encrypted)",
    },
    "schema.todo_write.desc": {
        "ja": (
            "セッション内タスクチェックリストを作成・更新する。3ステップ以上の複雑なタスクで使用すること。"
            "merge=falseで全リスト置換、merge=trueで既存リストにマージ（idで照合）。"
            "in_progressは同時に1つのみ許可。最大20アイテム。"
        ),
        "en": (
            "Create or update a structured task checklist for the current session. "
            "Use when a task requires 3 or more distinct steps. "
            "merge=false replaces the entire list; merge=true merges by id. "
            "Only one task may be in_progress at a time. Maximum 20 items."
        ),
    },
    "schema.todo_write.todos": {
        "ja": "タスクアイテムの配列",
        "en": "Array of todo items",
    },
    "schema.todo_write.id": {
        "ja": "タスクの一意識別子",
        "en": "Unique identifier for the todo item",
    },
    "schema.todo_write.content": {
        "ja": "タスクの内容・説明",
        "en": "Description/content of the todo item",
    },
    "schema.todo_write.status": {
        "ja": "タスクの状態 (pending=未着手, in_progress=実行中, completed=完了)",
        "en": "Task status (pending=not started, in_progress=working on, completed=done)",
    },
    "schema.todo_write.merge": {
        "ja": "trueで既存リストにマージ（idで照合し、変更のあるフィールドのみ更新）。falseで全置換。デフォルトfalse",
        "en": (
            "If true, merge into existing todos by id (update only changed fields). "
            "If false, replace the entire list. Default false."
        ),
    },
}
