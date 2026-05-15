# タスクボード（人間向けダッシュボード）

組織のオーナー（人間）がタスク全体を俯瞰するための共有ファイル。

## 目的

AnimaWorks のタスク管理は `task_queue.jsonl` + `current_state.md` + `delegate_task` で
エージェント間では完結しているが、**人間がひと目で全体を把握する手段がない**。
`shared/task-board.md` はこの問題を解決する人間向けダッシュボード。

## 位置づけ

| リソース | 用途 | 対象者 |
|---------|------|--------|
| `state/task_queue.jsonl` | タスク追跡（append-only） | エージェント |
| `state/current_state.md` | 現在の作業メモ | エージェント自身 |
| `state/task_results/` | タスク実行結果 | システム自動 |
| **`shared/task-board.md`** | **全タスク俯瞰** | **人間（オーナー）** |

## Human 向け文面ルール

TaskBoard に表示される `summary` / `title` / タスク名は、人間がそのカードだけを切り取って読んでも意味が分かる文面にする（MUST）。

- 1行目は案件名と現在状態をまとめる。内部ログ、委任経路、長い原文の貼り付けで始めない。
- 「誰が・何を・なぜ止まっているか／次に何をするか」を短く含める。
- `message id`、内部 task_id、長いファイルパス、ログ抜粋、`heartbeat` の詳細、文字化けした原文はカード表面に出さない。必要なら `instruction` / `description` / `context` 側に入れる。
- `delegate_task(summary=...)` と `submit_tasks(tasks[].title=...)` は TaskBoard のカード表面になる前提で、人間向けの短い日本語にする。
- 悪い例: `2026-05-15 09:00 JST定時タスクを確認。過去のnon-miyu delegation failure防止方針に従い...`
- 良い例: `朝の業務計画スクリプト実行が委任待ち。kanna が miyu の状態確認後に実行依頼する`

## フォーマット

```markdown
# タスクボード

最終更新: YYYY-MM-DD HH:MM by {更新者}

## 🔴 ブロック中（人間対応待ち）
| # | タスク | 担当 | ブロッカー | 期限 |
|---|--------|------|-----------|------|

## 🟡 進行中
| # | タスク | 担当 | 状態 | 期限 |
|---|--------|------|------|------|

## 📋 未着手（近日中）
| # | タスク | 担当 | 備考 | 期限 |
|---|--------|------|------|------|

## ✅ 今週完了
| タスク | 担当 | 完了日 |
|--------|------|--------|
```

## 運用ルール

1. **スーパーバイザー（CEO相当のAnima）が管理する**
   - タスク委任時: task-board.md に追記してから send_message
   - 完了報告を受けたら: 進行中 → 完了に移動
   - heartbeat 時: 期限超過チェック、ブロッカー状況更新

2. **各エージェントは自分のタスク完了時に更新する**
   - 進行中 → ✅ 今週完了 に移動

3. **週次リセット**
   - 「✅ 今週完了」セクションを前週分クリア
   - 未着手タスクの期限・優先度を見直し

## Slack 同期（オプション）

`slack_channel_post` と `slack_channel_update` ツールを使い、
Slack チャンネルのピン留めメッセージとして同期できる。
`slack_channel_update`（chat.update API）は通知を発生させずにメッセージを上書きするため、
ライブダッシュボードとして機能する。

> これらは gated アクション。使用するには permissions.json に
> `slack_channel_post: yes` / `slack_channel_update: yes` が必要。

### セットアップ手順

1. `slack_channel_post` で初回投稿 → 返ってきた `ts` を保存
2. Slack 上でそのメッセージをピン留め
3. 以降は `slack_channel_update` で上書き更新

### ts の保存先

`shared/task-board-slack.json` に保存:
```json
{"channel_id": "C0XXXXXXXX", "ts": "1741XXXXXXX.XXXXXX"}
```
