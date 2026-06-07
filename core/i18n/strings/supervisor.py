# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Domain-specific i18n strings."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "pending_executor.dep_result_header": {
        "ja": "## 先行タスク [{dep_id}] の結果",
        "en": "## Preceding task [{dep_id}] result",
    },
    "pending_executor.machine_directive": {
        "ja": (
            "🔴 MUST: machineツール使用が指定されたタスクです。\n5ステップ以上の重い処理は animaworks-tool machine run で外部エージェントに必ず委託し、\n出力を検証の上、不十分なら再度machineで修正してください。"
        ),
        "en": (
            "🔴 MUST: This task specifies the use of the machine tool.\nDelegate heavy work (5+ steps) to an external agent via animaworks-tool machine run.\nVerify the output and re-run machine if the result is insufficient."
        ),
    },
    "pending_executor.none_value": {
        "ja": "(なし)",
        "en": "(none)",
    },
    "pending_executor.task_completed": {
        "ja": "(タスク完了)",
        "en": "(task completed)",
    },
    "pending_executor.task_exec_end": {
        "ja": "タスク完了: {title} — {result}",
        "en": "Task completed: {title} — {result}",
    },
    "pending_executor.task_exec_start": {
        "ja": "タスク実行開始: {title}",
        "en": "Task execution started: {title}",
    },
    "pending_executor.task_fail_notify": {
        "ja": ("[タスク失敗通知]\nタスクID: {task_id}\nタスク: {title}\nエラー: {error}"),
        "en": ("[Task Failure]\nTask ID: {task_id}\nTask: {title}\nError: {error}"),
    },
    "pending_executor.provider_rate_limit_deferred": {
        "ja": "プロバイダ制限により再実行待ち",
        "en": "Waiting to retry due to provider rate limit",
    },
    "pending_executor.workspace_not_specified": {
        "ja": "(指定なし)",
        "en": "(not specified)",
    },
    "supervisor.zombie_reaped": {
        "ja": "zombie reaper: {count}個の子プロセスを回収しました",
        "en": "zombie reaper: reaped {count} child process(es)",
    },
}
