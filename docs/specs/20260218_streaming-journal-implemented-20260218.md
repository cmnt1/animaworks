# ストリーミングジャーナル — クラッシュ耐性のある応答出力永続化

## Overview

Animaのストリーミング応答出力を増分的にディスクへ書き出し（Write-Ahead Journal）、プロセスクラッシュ時の「記憶障害」を防止する。正常完了時はアクティビティログに統合して削除、クラッシュ復帰時は残存ジャーナルから部分応答を復元する。

依存: `20260218_unified-activity-log.md`（アクティビティログの `response_sent` / `error` イベントとして最終記録）

## Problem / Background

### 現状の問題

ストリーミング中のテキスト出力はメモリ上にのみ蓄積され、ディスクへの永続化は `cycle_done` 受信時まで行われない:

```
process_message_stream()
  │
  ├─ conv_memory.save()           ← ✅ ユーザー入力は保存済み
  │
  ├─ run_cycle_streaming()
  │    ├─ text_delta              ← ⚠️ partial_response (メモリのみ)
  │    ├─ tool_end → checkpoint   ← ✅ stream_checkpoint.json
  │    └─ cycle_done              ← ✅ ここで初めて conv_memory.save()
  │
  └─ finally:
       └─ if not cycle_done:
            conv_memory.append_turn(partial_response)
            ← ⚠️ Python例外時のみ。SIGKILL/OOM では実行されない
```

### 具体的に何が起きるか

1. **SIGKILL / OOM Killer**: `finally` ブロックが実行されず、ストリーミング中のテキストが全て失われる。Animaは「何を話していたか」を完全に忘れる
2. **長時間ストリーミング**: Mode A1 でツール実行を伴う長い応答（数分〜30分）の途中でクラッシュすると、ツール実行結果を含む大量の出力が消失する
3. **ユーザー体験**: 再起動後のAnimaは中断された会話の文脈を持たず、同じ作業を最初からやり直す可能性がある

### 影響を受けるコード箇所

| ファイル | 箇所 | 蓄積先 |
|---------|------|--------|
| `core/execution/agent_sdk.py:387-593` | `response_text: list[str]` | メモリのみ |
| `core/agent.py:677-943` | `full_text_parts: list[str]` | メモリ（tool_end時にcheckpointへ） |
| `core/anima.py:502-563` | `partial_response: str` | メモリ（finally時にconv_memoryへ） |

### 既存の部分的対策

- **StreamCheckpoint** (`shortterm/stream_checkpoint.json`): `tool_end` イベント時にテキストを保存。ただしツール間のテキスト出力は保存されない
- **finally ブロック** (`core/anima.py:556-563`): Python例外時には `partial_response` を保存。ハードクラッシュでは無効

## Solution

### 1. ストリーミングジャーナル（Write-Ahead Journal）

**ファイル配置:**
```
~/.animaworks/animas/{name}/shortterm/
└── streaming_journal.jsonl    ← NEW
```

単一ファイル、1応答サイクルに対して1ジャーナル。正常完了で削除されるため肥大化しない。

**レコード形式:**
```jsonl
{"ev":"start","ts":"2026-02-17T10:30:00","trigger":"message:sakura","from":"sakura","session_id":"abc123"}
{"ev":"text","ts":"2026-02-17T10:30:05","t":"承知しました。レポートを作成します。"}
{"ev":"text","ts":"2026-02-17T10:30:06","t":"まず市場データを検索します。"}
{"ev":"tool_start","ts":"2026-02-17T10:30:07","tool":"web_search","args_summary":"市場レポート 2026"}
{"ev":"tool_end","ts":"2026-02-17T10:30:15","tool":"web_search","result_summary":"5件取得"}
{"ev":"text","ts":"2026-02-17T10:30:16","t":"検索結果を基にレポートを構成します。"}
{"ev":"done","ts":"2026-02-17T10:31:00","summary":"市場レポートを作成し共有しました"}
```

**イベントタイプ:**

| ev | 説明 | フィールド |
|---|---|---|
| `start` | ストリーミング開始 | `trigger`, `from`, `session_id` |
| `text` | テキスト断片 | `t`（テキスト内容） |
| `tool_start` | ツール実行開始 | `tool`, `args_summary` |
| `tool_end` | ツール実行完了 | `tool`, `result_summary` |
| `done` | 正常完了 | `summary` |

**設計判断:**
- `text` イベントのフィールド名を `t` に短縮（I/O効率。1応答で数百〜数千チャンクの可能性）
- `done` イベント書き込み後にファイル削除。`done` が存在する = 正常完了確認済み

### 2. StreamingJournal クラス

```
core/memory/streaming_journal.py
```

**主要API:**

```python
class StreamingJournal:
    def __init__(self, anima_dir: Path): ...

    # ライフサイクル
    def open(self, trigger: str, from_person: str, session_id: str) -> None:
        """ジャーナルファイルを開き、startイベントを書き込む"""

    def write_text(self, text: str) -> None:
        """テキスト断片を追記。バッファリング付き"""

    def write_tool_start(self, tool: str, args_summary: str) -> None:
        """ツール開始イベントを追記"""

    def write_tool_end(self, tool: str, result_summary: str) -> None:
        """ツール完了イベントを追記"""

    def finalize(self, summary: str) -> None:
        """doneイベントを書き込み、ジャーナルファイルを削除"""

    def close(self) -> None:
        """ファイルハンドルを閉じる（finalize せずに閉じる = 異常終了マーカー）"""

    # リカバリ
    @classmethod
    def has_orphan(cls, anima_dir: Path) -> bool:
        """未完了のジャーナルが存在するか"""

    @classmethod
    def recover(cls, anima_dir: Path) -> JournalRecovery | None:
        """残存ジャーナルを読み込み、復元データを返す。ジャーナルは削除"""
```

**JournalRecovery データモデル:**

```python
@dataclass
class JournalRecovery:
    trigger: str              # 元のトリガー（例: "message:sakura"）
    from_person: str          # 送信者
    session_id: str           # セッションID
    started_at: str           # 開始タイムスタンプ
    recovered_text: str       # 連結されたテキスト
    tool_calls: list[dict]    # ツール実行履歴
    last_event_at: str        # 最後のイベントタイムスタンプ
    is_complete: bool         # done イベントが存在するか（通常 False）
```

### 3. バッファリング戦略

`text_delta` は高頻度（毎トークン）で発火するため、全チャンクを即座に書き込むとI/O負荷が高い。以下のバッファリング戦略を採用:

```python
class StreamingJournal:
    _FLUSH_INTERVAL_SEC = 1.0     # 最大1秒ごとにフラッシュ
    _FLUSH_SIZE_CHARS = 500       # 500文字蓄積でフラッシュ

    def write_text(self, text: str) -> None:
        self._buffer += text
        now = time.monotonic()
        if (len(self._buffer) >= self._FLUSH_SIZE_CHARS
                or now - self._last_flush >= self._FLUSH_INTERVAL_SEC):
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        self._write_event({"ev": "text", "t": self._buffer})
        self._buffer = ""
        self._last_flush = time.monotonic()
        self._fd.flush()
        os.fsync(self._fd.fileno())  # OSバッファもフラッシュ
```

**最悪ケースの損失量**: 直前のフラッシュから最大1秒 or 500文字分。ハードクラッシュでもほぼ全文が復元可能。

### 4. クラッシュリカバリフロー

**AnimaRunner起動時** (`core/supervisor/runner.py`):

```
AnimaRunner.run()
  │
  ├─ IPC server 起動
  ├─ DigitalAnima ロード
  │
  ├─ ★ StreamingJournal.has_orphan() チェック
  │    └─ True の場合:
  │         ├─ recovery = StreamingJournal.recover()
  │         ├─ conv_memory.append_turn("assistant",
  │         │     recovery.recovered_text + "\n[プロセスクラッシュにより応答が中断されました]")
  │         ├─ conv_memory.save()
  │         ├─ activity_logger.log("error",
  │         │     summary="プロセスクラッシュにより応答中断",
  │         │     meta={"recovered_chars": len(recovery.recovered_text),
  │         │           "trigger": recovery.trigger})
  │         └─ logger.warning("Recovered streaming journal: %d chars", ...)
  │
  ├─ スケジューラ開始
  └─ inbox watcher 開始
```

### 5. 既存コンポーネントとの関係

| コンポーネント | 関係 |
|---|---|
| **StreamCheckpoint** (`stream_checkpoint.json`) | **共存**。チェックポイントはリトライ用（セッション継続）、ジャーナルはクラッシュリカバリ用（記録保全）。役割が異なる |
| **ConversationMemory** | リカバリ時に `append_turn()` で中断応答を記録 |
| **ActivityLogger** (unified-activity-log) | 正常完了時: ジャーナル内容を要約して `response_sent` で記録。クラッシュ復帰時: `error` イベントで記録 |
| **ProcessSupervisor** | 変更不要。リカバリはAnimaRunner初期化時に自律的に実行 |

### 6. ストリーミングジャーナルの書き込みポイント

| 場所 | イベント | 説明 |
|---|---|---|
| `core/anima.py` process_message_stream() | `open()` | ストリーミング開始時（lock取得後） |
| `core/anima.py` process_message_stream() | `write_text()` | `text_delta` チャンク受信時 |
| `core/agent.py` run_cycle_streaming() | `write_tool_start()` | ツール実行開始時 |
| `core/agent.py` run_cycle_streaming() | `write_tool_end()` | ツール実行完了時 |
| `core/anima.py` process_message_stream() | `finalize()` | `cycle_done` 受信時（正常完了） |
| `core/anima.py` process_message_stream() | `close()` | finally ブロック（finalize未実行時のフォールバック） |

## Implementation Plan

### Phase 1: StreamingJournal 基盤

1. `core/memory/streaming_journal.py` — StreamingJournal クラス実装
   - `JournalRecovery` データモデル（dataclass）
   - `open()` / `write_text()` / `write_tool_start()` / `write_tool_end()` — 書き込みAPI
   - `finalize()` / `close()` — ライフサイクル終了
   - `has_orphan()` / `recover()` — リカバリAPI
   - バッファリング（1秒 / 500文字、`os.fsync()`）
2. テスト: `tests/test_streaming_journal.py`
   - 正常フロー（open → write → finalize → ファイル削除確認）
   - クラッシュシミュレーション（open → write → close（finalizeなし）→ recover）
   - バッファリング（フラッシュ条件の検証）
   - エッジケース（空ジャーナル、破損JSONL行のスキップ）

### Phase 2: ストリーミングへの組み込み

3. `core/anima.py` — `process_message_stream()` にジャーナル書き込み追加
   - lock取得後に `journal.open()`
   - `text_delta` で `journal.write_text()`
   - `cycle_done` で `journal.finalize()`
   - finally で `journal.close()`（フォールバック）
4. `core/agent.py` — `run_cycle_streaming()` にツールイベント書き込み追加
   - `tool_start` / `tool_end` でジャーナルに記録
   - StreamingJournal インスタンスは AgentCore に注入（DigitalAnima から渡す）

### Phase 3: クラッシュリカバリ

5. `core/supervisor/runner.py` — AnimaRunner初期化時のリカバリ処理
   - `StreamingJournal.has_orphan()` チェック
   - `recover()` → ConversationMemory に中断応答として記録
   - ActivityLogger への `error` イベント記録（unified-activity-log 実装後に有効化）

### Phase 4: heartbeat / cron への拡張

6. `core/anima.py` — `run_heartbeat()` にもジャーナル適用
   - heartbeat も長時間ストリーミングする可能性があるため同様にジャーナル化
7. `core/anima.py` — `run_cron_task()` にもジャーナル適用（同上）

## Scope

### In Scope

- StreamingJournal クラスの新規実装（`core/memory/streaming_journal.py`）
- `process_message_stream()` / `run_cycle_streaming()` へのジャーナル書き込み組み込み
- AnimaRunner起動時のクラッシュリカバリ（orphanジャーナル検出・復元）
- heartbeat / cron のジャーナル化
- テスト

### Out of Scope

- ActivityLogger への統合記録（unified-activity-log Issue で対応。ジャーナル側は `activity_logger.log()` の呼び出しポイントのみ用意）
- WebSocket経由でのクライアントへのリカバリ通知（将来検討）
- ジャーナルの暗号化・圧縮（現時点では不要）
- Mode A2 / Mode B のジャーナル化（非ストリーミングのため `finally` ブロックで十分）

## Risk

- **I/O負荷**: `os.fsync()` は重い操作。バッファリング（1秒/500文字）で軽減しているが、低スペック環境ではストリーミング速度に影響する可能性がある。`fsync` の頻度を設定可能にすることで対応
- **ジャーナル破損**: ハードクラッシュ時にJSONL行が途中で切れる可能性。`recover()` で破損行をスキップする実装が必要
- **二重リカバリ**: ProcessSupervisor の再起動が高速（2秒バックオフ）な場合、リカバリ処理が間に合うか。リカバリはAnima初期化時の同期処理なので問題なし
- **ディスク容量**: 1ジャーナルは1応答分（通常数KB〜数百KB）。`finalize()` で即削除されるため肥大化リスクは低い
