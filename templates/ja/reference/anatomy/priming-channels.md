# Priming チャネル技術リファレンス

既定の `compact` は送信者、タスク、常駐知識を取得し、条件を満たす場合だけ関連知識を検索する。オプトインの `full` は最近の活動とエピソードも取得する。チャネル構成は `priming.profile` で選択され、すべてのトリガーで全チャネルが動くわけではない。

`PrimingEngine` が取得するチャネルと予算の仕様を示す。C0（important_knowledge）は Channel C の知識パイプライン内の補助ブロック。

## チャネル一覧

| チャネル | ソース | trust |
|---------|--------|-------|
| A: sender_profile | `shared/users/{sender}/index.md` | medium |
| B: recent_activity | `activity_log/` + shared channels | trusted |
| C: related_knowledge | RAG ベクトル検索（knowledge + common_knowledge） | medium / untrusted |
| C0: important_knowledge | `[IMPORTANT]` タグ付きチャンク | medium |
| E: pending_tasks | TaskStore + task results | trusted |
| F: episodes | RAG ベクトル検索（episodes/） | medium |

追加注入:

| 項目 | ソース | trust |
|------|--------|-------|
| Recent outbound | activity_log（最大3件、`channel_post` / `message_sent`） | trusted |
| Pending human notifications | `human_notify` イベント | trusted |

スキル・手続きの本文は Priming では注入されない。システムプロンプトのスキルカタログに示されたパス（例: `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`）を `read_memory_file` で読み込む。

---

## Channel A: sender_profile

送信者のユーザープロファイルを注入する。

- **ソース**: `shared/users/{sender}/index.md` を直接読み取り
- **上限**: `min(400, max_tokens // 4)`
- **送信者不明時**: スキップ

---

## Channel B: recent_activity

直近の活動タイムラインを注入する。

- **ソース**: `activity_log/{date}.jsonl` + 共有チャネルの最新投稿

**Priming 注入と明示検索の違い**: Channel B は `full` プロファイルで取得する。過去の行動ログをキーワードで広く探す用途は `search_memory(scope="activity_log")` を使う。注入とツール検索は別の経路である。

### トリガー別フィルタリング

| トリガー | 除外されるイベントタイプ |
|---------|----------------------|
| `heartbeat` / `cron` / `inbox` / `task` | `tool_use`, `tool_result`, `heartbeat_start`, `heartbeat_reflection`, `inbox_processing_start`, `inbox_processing_end` |
| その他 | `tool_use`, `tool_result`, `memory_write`, `cron_executed`, `heartbeat_start`, `heartbeat_end`, `heartbeat_reflection`, `inbox_processing_start`, `inbox_processing_end` |

---

## Channel C: related_knowledge

RAG ベクトル検索で関連知識を注入する。

- **検索方式**: Dual-query（メッセージコンテキスト + キーワードのみ）
- **検索対象**: 個人 `knowledge/` + `shared_common_knowledge` コレクション
- **最小スコア**: `config.json` の `rag.min_retrieval_score`（デフォルト 0.3）

### trust 分離

検索結果はチャンクの `origin` に基づいて trust レベルで分離される:

| trust | 対象 | 処理 |
|-------|------|------|
| `medium` | 個人 knowledge、common_knowledge | 優先的に予算を消費 |
| `untrusted` | 外部プラットフォーム由来（`origin_chain` に `external_platform` を含む） | 残り予算で注入。`origin=ORIGIN_EXTERNAL_PLATFORM` タグ付き |

---

## Channel C0: important_knowledge

`[IMPORTANT]` タグ付きチャンクの概要ポインタを注入する。

- **対象**: `knowledge/` 内の `[IMPORTANT]` タグ付きチャンク
- **注入形式**: 概要ポインタ。詳細は `read_memory_file` で取得
- **用途**: 重要な業務ルール・判断基準の想起

---

## Channel E: pending_tasks

タスクキューの要約を注入する。

- **上限**: `min(500, max_tokens // 3)`
- **ソース**: `TaskQueueManager.format_for_priming()`
- **内容**:
  - `pending` / `in_progress` タスクの一覧と要約
  - 人間が起票したタスクに 🔴 HIGH マーカー
  - 30分以上更新がないタスクに ⚠️ STALE マーカー
  - 委譲タスクの状態
  - `task_results/` からの完了タスク結果

---

## Channel F: episodes

RAG ベクトル検索で関連エピソードを注入する。

- **検索対象**: `episodes/` コレクション
- **最小スコア**: Channel C と共通（`rag.min_retrieval_score`）

---

## 予算とプロファイル

`config.json` の `priming.profile` は `compact` または `full` を指定する（デフォルト: `compact`）。Anima ごとの `status.json` に `priming_profile` を指定すると、その設定が優先される。`priming.max_tokens` は想起のトークン予算（デフォルト: 2000）、`priming.channel_timeout_seconds` はチャネルごとの取得タイムアウト（デフォルト: 60秒）。

- `compact` は A（送信者）、E（タスク）、C0（常駐知識）、最近の送信、保留中の人間通知を取得する。C（関連知識）は chat/task トリガー、または question/request/delegation 意図があり、メッセージがある場合に取得する。B（最近の活動）・F（エピソード）・G（並列タスク表示）は取得しない。
- `full` は A / B / C0 / C / E / F と最近の送信、人間通知を取得する。
- A の上限は `min(400, max_tokens // 4)`、E の上限は `min(500, max_tokens // 3)`。最近の送信は最大3件・250トークン。`full` のチャネル項目と `compact` の関連知識は、`max_tokens` の残り枠に収める。
- 保留中の人間通知は想起予算とは別に扱われる。

---

## Hebbian LTP（長期増強）

Priming で検索・表示されたチャンクは `record_access(kind="retrieved")` により軽量な検索記録が更新される。`read_memory_file` や outcome 報告による明示的な使用は `used` として記録され、忘却保護はこの明示使用を基準にする。
