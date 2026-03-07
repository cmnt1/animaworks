# Unified Activity Log: 仕様準拠修正（6項目）

## Overview

統一アクティビティログの実装を `docs/memory.md` 及び実装仕様と照合した結果、6項目の未実装・差異を検出した。本番環境では `activity_log/` がまだ一度も生成されていないため、後方互換性を考慮せず修正可能。

## Problem / Background

仕様準拠調査で以下が判明:

- `run_cron_command()` のcron実行がアクティビティタイムラインに記録されない
- 仕様上13イベントタイプのうち `memory_write` と `error` の2タイプが未実装
- JOSNLフィールド名が他のJSONL（チャネル、DMログ）と不整合
- レガシー `heartbeat_history/` を読み続けるが、書き込みは `activity_log` に移行済みで陳腐化する
- 置き換え済みのデッドコードが残存

**本番状況（2026-02-17時点）:**

| データ | 状態 |
|--------|------|
| `activity_log/` | 未生成（全Anima） |
| `heartbeat_history/` | 全11Anima分存在（2/16-2/17） |
| `transcripts/` | 全Anima分存在 |
| `dm_logs/` | 未生成 |

→ `activity_log` は本番未稼働のため、フィールド名変更・レガシー削除すべて安全に実行可能。

## Implementation Details

### Fix 1: `run_cron_command()` にアクティビティログ追加

**対象:** `core/anima.py:942-1040`

**変更内容:** `run_cron_task()` (line 920-925) と同じパターンで `cron_executed` を記録する。

正常完了パス（line 1023付近）:
```python
try:
    activity = ActivityLogger(self.anima_dir)
    activity.log(
        "cron_executed",
        summary=f"コマンド: {task_name}",
        meta={"task_name": task_name, "exit_code": exit_code},
    )
except Exception:
    pass
```

エラーパス（line 1002付近）でも同様に記録。`exit_code=1` と `stderr` をメタデータに含める。

---

### Fix 2: `memory_write` / `error` イベントタイプ実装

#### 2a: `memory_write` イベント

**対象:** `core/tooling/handler.py:364-408` (`_handle_write_memory_file()`)

**変更内容:** ファイル書き込み成功後に記録:
```python
try:
    activity = ActivityLogger(self._anima_dir)
    activity.log(
        "memory_write",
        summary=f"{rel} ({args.get('mode', 'overwrite')})",
        meta={"path": rel, "mode": args.get("mode", "overwrite")},
    )
except Exception:
    pass
```

#### 2b: `error` イベント（5箇所全部）

**対象と変更内容:**

| # | 場所 | Phase | 既存ロジック |
|---|------|-------|-------------|
| 1 | `core/anima.py:371-372` | `process_message` | `logger.exception()` のみ |
| 2 | `core/anima.py:525-538` | `process_message_stream` | エラー分類済み (`TOOL_ERROR`/`LLM_ERROR`/`STREAM_ERROR`) |
| 3 | `core/anima.py:880-881` | `run_heartbeat` | `logger.exception()` のみ |
| 4 | `core/anima.py:932-935` | `run_cron_task` | `logger.exception()` のみ |
| 5 | `core/anima.py:1002-1007` | `run_cron_command` | `stderr` に例外情報記録済み |

各箇所に以下のパターンを追加:
```python
try:
    activity = ActivityLogger(self.anima_dir)
    activity.log(
        "error",
        summary=f"{phase}エラー: {type(exc).__name__}",
        meta={"phase": phase, "error": str(exc)[:200]},
    )
except Exception:
    pass
```

`process_message_stream` (箇所2) は既存の `error_code` 分類を活用:
```python
meta={"phase": "process_message_stream", "error_code": error_code, "error": str(exc)[:200]}
```

---

### Fix 3: JOSNLフィールド名を `from`/`to` に統一

**対象:** `core/memory/activity.py`

#### 3a: `to_dict()` の出力変換 (line 51-54)

```python
def to_dict(self) -> dict[str, Any]:
    d = asdict(self)
    d = {k: v for k, v in d.items() if v}
    # Python予約語回避: from_person -> from, to_person -> to
    if "from_person" in d:
        d["from"] = d.pop("from_person")
    if "to_person" in d:
        d["to"] = d.pop("to_person")
    return d
```

#### 3b: 読み込み側 `recent()` のマッピング (line 173-176)

`ActivityEntry` コンストラクタに渡す前にキー変換:
```python
raw = json.loads(line)
# JSONL上の from/to を Python field名に変換
if "from" in raw:
    raw["from_person"] = raw.pop("from")
if "to" in raw:
    raw["to_person"] = raw.pop("to")
entries.append(ActivityEntry(**{
    k: v for k, v in raw.items()
    if k in ActivityEntry.__dataclass_fields__
}))
```

#### 3c: `_involves()` のキー名更新 (line 189-196)

呼び出し元で既にマッピング済みの `ActivityEntry` を使う場合は変更不要。
raw dict を直接渡す場合は `raw.get("from")` / `raw.get("to")` に変更。

---

### Fix 4: 記録ポイントの間接性 — 修正不要

ACKメッセージ等のツールハンドラ非経由パスは低重要度。レビューで承認済みの設計判断として維持。

---

### Fix 5: デッドコード削除

#### 5a: `_append_dm_log` 削除

**対象:** `core/messenger.py:204-219`

メソッド本体を削除。呼び出し元はゼロ（grep確認済み）。

#### 5b: `_append_transcript` 削除

**対象:** `core/memory/conversation.py:153-176`

メソッド本体を削除。

**テスト削除:** `tests/unit/core/memory/test_conversation.py:142-150` の `test_append_transcript` テストも削除。

#### 5c: 関連ヘルパーの確認

`_get_dm_log_path()` 等、`_append_dm_log` からのみ呼ばれるヘルパーがあれば併せて削除。ただし `read_dm_history()` のレガシーフォールバックで使用されている場合は残す。

---

### Fix 6: `_load_heartbeat_history()` を ActivityLogger に置換

**対象:** `core/anima.py:211-239`

#### 変更内容

メソッド全体を書き換え。レガシーフォールバックなし:

```python
def _load_heartbeat_history(self) -> str:
    """Load last N heartbeat history entries from unified activity log."""
    try:
        activity = ActivityLogger(self.anima_dir)
        entries = activity.recent(
            days=2,
            types=["heartbeat_end"],
            limit=self._HEARTBEAT_HISTORY_N,
        )
        if not entries:
            return ""
        lines = []
        for e in entries:
            ts_short = e.ts[11:19] if len(e.ts) >= 19 else e.ts
            summary = (e.summary or e.content)[:200]
            lines.append(f"- {ts_short}: {summary}")
        return "\n".join(lines)
    except Exception:
        logger.exception("Failed to load heartbeat history from activity log")
        return ""
```

#### 不要になる定数・コード

- `_HEARTBEAT_HISTORY_DIR` 定数 — 削除可能（`shortterm/heartbeat_history` パス）
- `_purge_old_heartbeat_logs()` — 既にH-3で削除済み
- `_save_heartbeat_history()` — 既にH-3で削除済み

**注意:** `heartbeat_history` プロンプトテンプレートの `{history}` 変数フォーマットが変わるため、テンプレートとの整合性を確認すること。旧フォーマット `- TIMESTAMP: [action] summary` → 新フォーマット `- HH:MM:SS: summary`。

## Testing

### 新規テスト

- Fix 1: `run_cron_command` の `cron_executed` 記録を確認するユニットテスト
- Fix 2a: `write_memory_file` 実行後に `memory_write` エントリが存在するテスト
- Fix 2b: エラー発生時に `error` エントリが記録されるテスト（少なくとも `process_message` と `process_message_stream` の2パス）
- Fix 3: `to_dict()` が `from`/`to` キーで出力し、`recent()` で正しく読み戻せるラウンドトリップテスト
- Fix 6: `_load_heartbeat_history()` が `activity_log` の `heartbeat_end` エントリを読むテスト

### 既存テスト修正

- Fix 5: `test_conversation.py` の `test_append_transcript` テスト削除
- Fix 3: `test_activity.py` の `test_entry_to_dict_full` — `from_person`/`to_person` → `from`/`to` アサーション変更
- Fix 6: `test_heartbeat_dialogue_e2e.py` の関連テスト — ActivityLogger経由のデータを前提に更新

## References

- 仕様準拠調査レポート: 本セッション内（2026-02-17実施）
- 実装仕様: `docs/specs/20260218_unified-activity-log-implemented-20260218.md`
- メモリシステム仕様: `docs/memory.md`
- 承認済みレビュー: `docs/specs/20260218_review_unified-activity-log_approved-20260218.md`
