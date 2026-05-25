from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""i18n strings for tmp cleanup CLI."""

STRINGS: dict[str, dict[str, str]] = {
    "tmp.list_header": {
        "ja": "tmp ディレクトリ: {path}",
        "en": "tmp directory: {path}",
    },
    "tmp.list_empty": {
        "ja": "  (空)",
        "en": "  (empty)",
    },
    "tmp.list_summary": {
        "ja": "  合計: {size} / {count} 件",
        "en": "  Total: {size} / {count} items",
    },
    "tmp.list_entry": {
        "ja": "  {size:>8}  {age}  {name}{kind}",
        "en": "  {size:>8}  {age}  {name}{kind}",
    },
    "tmp.list_entry_dir": {
        "ja": "/",
        "en": "/",
    },
    "tmp.clean_requires_filter": {
        "ja": "削除条件を指定してください: --older-than, --min-size, または --all",
        "en": "Specify a cleanup filter: --older-than, --min-size, or --all",
    },
    "tmp.clean_requires_force": {
        "ja": "全削除には --all と --force が必要です",
        "en": "Full cleanup requires both --all and --force",
    },
    "tmp.clean_header": {
        "ja": "tmp 整理: {path}",
        "en": "Cleaning tmp: {path}",
    },
    "tmp.clean_dry_run": {
        "ja": "[DRY RUN] 削除対象: {count} 件 ({size})",
        "en": "[DRY RUN] Would remove: {count} items ({size})",
    },
    "tmp.clean_done": {
        "ja": "削除完了: {count} 件 ({size})",
        "en": "Removed: {count} items ({size})",
    },
    "tmp.clean_skipped": {
        "ja": "スキップ: {count} 件",
        "en": "Skipped: {count} items",
    },
    "tmp.clean_error": {
        "ja": "  エラー: {message}",
        "en": "  Error: {message}",
    },
    "tmp.invalid_size": {
        "ja": "サイズ指定が不正です: {value}",
        "en": "Invalid size value: {value}",
    },
    "tmp.age_days": {
        "ja": "{days}日前",
        "en": "{days}d ago",
    },
    "tmp.age_hours": {
        "ja": "{hours}時間前",
        "en": "{hours}h ago",
    },
    "tmp.age_recent": {
        "ja": "直近",
        "en": "recent",
    },
}
