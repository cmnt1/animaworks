# Priming チャネル技術リファレンス

Priming は compact の単一路線で動作する。送信者・タスク・常駐知識・直近の送信・人間向け通知を取得し、条件を満たす場合は関連知識も検索する。heartbeat / inbox / cron では、共通の上限設定に従って最近の活動やエピソードも取得する。

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

**Priming 注入と明示検索の違い**: Channel B は heartbeat / inbox / cron の compact な背景想起で、共通設定の上限内で取得する。過去の行動ログをキーワードで広く探す用途は `search_memory(scope="activity_log")` を使う。注入とツール検索は別の経路である。

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

## 予算と設定

プロファイル選択はなく、Priming は常に compact の取得経路を使う。`priming.max_tokens` は想起予算（デフォルト: 2000）、`priming.channel_timeout_seconds` はチャネルごとの取得タイムアウト（デフォルト: 60秒）。`compact_background_recall` は heartbeat / inbox / cron で共有する1組の上限で、`compact_background_recall_enabled` で一括して無効化できる。

- A（送信者）は `min(400, max_tokens // 4)`、E（タスク）は `min(500, max_tokens // 3)` が上限。最近の送信は最大3件・250トークン。
- C（関連知識）は chat/task トリガー、または question/request/delegation 意図があり、メッセージがある場合に取得する。
- B（最近の活動）は heartbeat / inbox / cron で設定上限内に取得する。F（エピソード）は同じトリガーでメッセージがあり、関連取得が有効な場合に設定上限内で取得する。
- 保留中の人間通知は想起予算とは別に扱われる。

---

## Hebbian LTP（長期増強）

Priming で検索・表示されたチャンクは `record_access(kind="retrieved")` により軽量な検索記録が更新される。`read_memory_file` や outcome 報告による明示的な使用は `used` として記録され、忘却保護はこの明示使用を基準にする。
