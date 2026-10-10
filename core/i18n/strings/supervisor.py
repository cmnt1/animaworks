# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Domain-specific i18n strings."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "pending_executor.stale_backlog": {
        "ja": (
            "[滞留タスク通知]\nタスクID: {task_id}\nタスク: {title}\n"
            "24時間以上進捗がなく、実行入力も未登録です。このままでは自動実行されません。"
            "必要な作業は submit_tasks に同じタスクIDと実行入力を渡して登録してください。"
            "不要・実行不能なら cancelled にし、理由を依頼者へ伝えてください。重複起票はしないでください。"
        ),
        "en": (
            "[Stale Task]\nTask ID: {task_id}\nTask: {title}\n"
            "No progress for 24 hours and no execution input. This task cannot run automatically. "
            "Publish its input through submit_tasks using the same task ID, or cancel and explain to the requester. "
            "Do not create a duplicate task."
        ),
        "ko": (
            "[장기 미처리 작업]\n작업 ID: {task_id}\n작업: {title}\n"
            "24시간 이상 진행이 없고 실행 입력도 없습니다. 자동 실행되지 않습니다. "
            "submit_tasks에 같은 작업 ID와 입력을 등록하거나 취소하고 요청자에게 이유를 알리세요. 중복 생성하지 마세요."
        ),
    },
    "pending_executor.stale_incomplete": {
        "ja": (
            "[滞留タスク通知]\nタスクID: {task_id}\nタスク: {title}\n"
            "24時間以上進捗がなく、実行が停止したままです。pending と表示されても再実行予約ではありません。"
            "実行済みの操作・成果と最新の追加依頼を確認してください。継続するなら "
            "update_task(task_id='{task_id}', status='pending', resume=True) で明示的に再開してください。"
            "不要・実行不能なら cancelled にし、理由を依頼者へ伝えてください。重複起票や未確認の完了扱いはしないでください。"
        ),
        "en": (
            "[Stale Task]\nTask ID: {task_id}\nTask: {title}\n"
            "No progress for 24 hours; execution is stopped. Pending does not mean queued for execution. "
            "Check existing effects, artifacts and follow-up requests. To continue, explicitly call "
            "update_task(task_id='{task_id}', status='pending', resume=True). "
            "Otherwise cancel and explain to the requester. Do not duplicate or declare unverified completion."
        ),
        "ko": (
            "[장기 미처리 작업]\n작업 ID: {task_id}\n작업: {title}\n"
            "24시간 이상 진행이 없고 실행이 중단되었습니다. pending은 실행 예약이 아닙니다. "
            "기존 조치·결과와 추가 요청을 확인하고 계속하려면 "
            "update_task(task_id='{task_id}', status='pending', resume=True)를 호출하세요. "
            "불필요하거나 실행 불가라면 취소하고 요청자에게 이유를 알리세요. 중복 생성이나 미검증 완료 처리는 하지 마세요."
        ),
    },
    "pending_executor.dep_result_header": {
        "ja": "## 先行タスク [{dep_id}] の結果",
        "en": "## Preceding task [{dep_id}] result",
    },
    "pending_executor.none_value": {
        "ja": "(なし)",
        "en": "(none)",
    },
    "pending_executor.task_cancelled": {
        "ja": "タスクはキャンセルされました",
        "en": "Task was cancelled",
        "ko": "작업이 취소되었습니다",
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
    "pending_executor.model_override": {
        "ja": "タスクのモデル上書き: {requested} で実行（解決: {resolved}）",
        "en": "Task model override: running with {requested} (resolved: {resolved})",
        "ko": "태스크 모델 오버라이드: {requested}로 실행 (해결: {resolved})",
    },
    "pending_executor.task_fail_notify": {
        "ja": (
            "[タスク失敗通知]\nタスクID: {task_id}\nタスク: {title}\nエラー: {error}\n"
            "実行済みの操作・成果を確認してください。元の入力は保存されていますが、自動再実行はされません。"
            "継続するなら update_task(task_id='{task_id}', status='pending', resume=True) で再開してください。"
            "不要・実行不能なら cancelled にし、理由を依頼者へ伝えてください。"
        ),
        "en": (
            "[Task Failure]\nTask ID: {task_id}\nTask: {title}\nError: {error}\n"
            "Check existing effects and artifacts. Original input is retained, but execution is not automatically retried. "
            "To continue, call update_task(task_id='{task_id}', status='pending', resume=True). "
            "Otherwise cancel and explain to the requester."
        ),
        "ko": (
            "[작업 실패 알림]\n작업 ID: {task_id}\n작업: {title}\n오류: {error}\n"
            "기존 조치와 결과를 확인하세요. 원래 입력은 보존되지만 자동 재시도되지 않습니다. "
            "계속하려면 update_task(task_id='{task_id}', status='pending', resume=True)를 호출하세요. "
            "불필요하거나 실행 불가라면 취소하고 요청자에게 이유를 알리세요."
        ),
    },
    "pending_executor.task_undeclared_notify": {
        "ja": (
            "[タスク未完了通知]\nタスクID: {task_id}\nタスク: {title}\n"
            "実行は正常に終わりましたが、完了（done）・取り消し（cancelled）・待ち（pending）の宣言がありませんでした。"
            "実行済みの操作・成果を確認してください。元の入力は保存されていますが、自動再実行はされません。"
            "継続するなら update_task(task_id='{task_id}', status='pending', resume=True) で再開してください。"
            "不要・実行不能なら cancelled にし、理由を依頼者へ伝えてください。"
        ),
        "en": (
            "[Task Not Closed]\nTask ID: {task_id}\nTask: {title}\n"
            "The run ended normally without declaring done, cancelled, or pending. "
            "Check existing effects and artifacts. Original input is retained, but execution is not automatically retried. "
            "To continue, call update_task(task_id='{task_id}', status='pending', resume=True). "
            "Otherwise cancel and explain to the requester."
        ),
        "ko": (
            "[작업 미완료 알림]\n작업 ID: {task_id}\n작업: {title}\n"
            "실행은 정상 종료되었지만 완료(done)·취소(cancelled)·대기(pending) 선언이 없었습니다. "
            "기존 조치와 결과를 확인하세요. 원래 입력은 보존되지만 자동 재시도되지 않습니다. "
            "계속하려면 update_task(task_id='{task_id}', status='pending', resume=True)를 호출하세요. "
            "불필요하거나 실행 불가라면 취소하고 요청자에게 이유를 알리세요."
        ),
    },
    "pending_executor.workspace_not_specified": {
        "ja": "(指定なし)",
        "en": "(not specified)",
    },
    "pending_executor.submitted_line": {
        "ja": "提出: {time}（経過 {elapsed}）",
        "en": "Submitted: {time} (elapsed {elapsed})",
        "ko": "제출: {time} (경과 {elapsed})",
    },
    "pending_executor.elapsed": {
        "ja": "{hours}時間{minutes}分",
        "en": "{hours}h {minutes}m",
        "ko": "{hours}시간 {minutes}분",
    },
    "supervisor.zombie_reaped": {
        "ja": "zombie reaper: {count}個の子プロセスを回収しました",
        "en": "zombie reaper: reaped {count} child process(es)",
    },
}
