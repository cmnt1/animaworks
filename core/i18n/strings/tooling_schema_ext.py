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
        "ja": (
            "承認・レビュー・報告・Inbox整理は別タスクで管理し、完了済み作業をpendingへ戻さない。元の作業自体を再実行する場合のみ status='pending', resume=true を明示する。タスクのステータスを更新する。完了時は status='done'、中断時は status='cancelled' に設定する。委譲したタスクには status='cancelled'（取り下げ）だけ指定できる。"
            "pending で終える時は何を待っているかを waiting_for に書くと、それが起きた時に自動で再開される。"
            "範囲を狭める・広げる・分ける時は scope_note に書くと依頼元に伝わる。"
        ),
        "en": (
            "Track approval, review, reporting and inbox cleanup as separate tasks; do not reopen completed work. Only to rerun the original work, explicitly set status='pending', resume=true. Update a task's status. Set status='done' on completion, status='cancelled' on abort. For a task you delegated, only status='cancelled' (withdraw the request) is allowed. "
            "When ending as pending, put what you are waiting for in waiting_for so the task resumes automatically when it happens. "
            "When narrowing, widening, or splitting the scope, write it in scope_note to inform the requester."
        ),
        "ko": (
            "승인·검토·보고·Inbox 정리는 별도 작업으로 관리하고 완료된 작업을 pending으로 되돌리지 않는다. 원래 작업 자체를 재실행할 때만 status='pending', resume=true를 명시한다. 작업 상태를 업데이트한다. 완료 시 status='done', 중단 시 status='cancelled'로 설정한다. 위임한 작업에는 status='cancelled'(요청 철회)만 지정할 수 있다. "
            "pending으로 끝낼 때 무엇을 기다리는지 waiting_for에 적으면 해당 사건이 발생했을 때 자동으로 재개된다. "
            "범위를 좁히거나 넓히거나 나눌 때는 scope_note에 적으면 요청자에게 전달된다."
        ),
    },
    "schema.update_task.waiting_for": {
        "ja": "pending で終える時に何を待っているか（kind=task/time/message/external）。task/time は満たされると自動で再開される。",
        "en": "What the task is waiting for when ending as pending (kind=task/time/message/external). task/time waits resume automatically when satisfied.",
        "ko": "pending으로 끝낼 때 기다리는 대상(kind=task/time/message/external). task/time 대기는 충족되면 자동 재개된다.",
    },
    "schema.update_task.waiting_for_kind": {
        "ja": "待ちの種類（task=タスク完了, time=時刻, message=返事, external=外部の出来事）",
        "en": "Wait kind (task=task finished, time=timestamp, message=reply, external=external event)",
        "ko": "대기 종류(task=태스크 완료, time=시각, message=회신, external=외부 사건)",
    },
    "schema.update_task.waiting_for_ref": {
        "ja": "待つ対象（task はタスクID、message は相手、external は自由文字列）",
        "en": "What to wait for (task ID for task, person for message, free text for external)",
        "ko": "기다리는 대상(task는 태스크 ID, message는 상대, external은 자유 문자열)",
    },
    "schema.update_task.waiting_for_until": {
        "ja": "待つ期限の ISO8601 時刻（kind=time では必須）",
        "en": "ISO8601 timestamp to wait until (required for kind=time)",
        "ko": "대기 기한의 ISO8601 시각(kind=time에서 필수)",
    },
    "schema.update_task.scope_note": {
        "ja": "受け手が決めた範囲メモ（狭める・広げる・分ける内容）。履歴に追記され、依頼元に1通通知される。",
        "en": "The receiver's scope note (narrowing, widening, or splitting). Appended to history and sent once to the requester.",
        "ko": "수신자가 정한 범위 메모(좁히기·넓히기·나누기). 이력에 추가되고 요청자에게 한 번 알린다.",
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
