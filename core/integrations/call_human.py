from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI adapter for the ``call_human`` ToolHandler capability."""

import argparse
import sys
from typing import Any

from core.integrations._comm_cli import cli_main_safely


def get_cli_guide() -> str:
    """Return CLI guide text for the tool guide injection."""
    return """\
### call_human — 人間への緊急通知

重要な問題や判断が必要な事項を人間の管理者に通知します。

```
animaworks-tool call_human "件名" "本文" [--priority PRIORITY]
```

**優先度 (--priority):** `low` / `normal`（デフォルト）/ `high` / `urgent`

**確認キー (--sha):** 外部通知チャネルがある場合、各セッションの初回は送信されずに8桁のキーが返ります。表示された指示どおり調査し、人間への通知が必要な場合だけ `--sha キー` を付けて再実行してください。確認サーバーに接続できない場合は送信されません。

**例:**
```bash
# 通常通知
animaworks-tool call_human "タスク完了" "エアコン価格調査が完了しました"

# 緊急通知
animaworks-tool call_human "障害発生" "本番APIが503を返しています" --priority urgent
```

**いつ使うか:**
- 障害・エラーの検出（自力解決不可）
- 部下からのエスカレーション受領後、事実確認して重要と判断した場合
- 人間の判断が必要な意思決定
- 重要タスクの完了報告

**使わない場合:** 定常巡回で問題なし、軽微な自動修復完了"""


@cli_main_safely
def cli_main(args: list[str]) -> None:
    """Parse the legacy CLI flags and delegate to the canonical tool handler."""
    parser = argparse.ArgumentParser(
        prog="animaworks-tool call_human",
        description="Send human escalation notification",
    )
    parser.add_argument("subject", help="Notification subject")
    parser.add_argument("body", help="Notification body")
    parser.add_argument(
        "--priority",
        choices=["low", "normal", "high", "urgent"],
        default="normal",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Send an interactive approval request (buttons where supported)",
    )
    parser.add_argument(
        "--callback-id",
        default="",
        help="Stable callback id for interactive mode (auto-generated if omitted)",
    )
    parser.add_argument(
        "--options",
        default="approve,reject,comment",
        help="Comma-separated button labels for interactive mode",
    )
    parser.add_argument(
        "--category",
        default="approval",
        help="Interaction category label",
    )
    parser.add_argument(
        "--sha",
        default="",
        help="Confirmation key returned by the first call in this session",
    )
    ns = parser.parse_args(args)

    tool_args: dict[str, Any] = {
        "subject": ns.subject,
        "body": ns.body,
        "priority": ns.priority,
        "interactive": ns.interactive,
        "category": ns.category,
        "options": [option.strip() for option in ns.options.split(",") if option.strip()],
    }
    if ns.sha:
        tool_args["sha"] = ns.sha
    if ns.callback_id:
        tool_args["callback_id"] = ns.callback_id

    # Keep the core integration layer independent of the CLI package. The
    # standalone runner is also re-exported by cli._anima_tool for adapters.
    from core.tooling.standalone import run_tool_for_current_anima, tool_result_is_error

    result = run_tool_for_current_anima("call_human", tool_args)
    print(result)
    if tool_result_is_error(result):
        sys.exit(1)


__all__ = ["cli_main", "get_cli_guide"]
