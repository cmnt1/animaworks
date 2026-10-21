# Inboxで受けた依頼を実行タスクにつなげる

## 対象と前提

DiscordなどからInboxに届く、ユーザーが許可した調査・検証・作業が対象。
`inbox` と `inbox:<sender>` は `submit_tasks` を公開する。
TaskExec (`task:*`)・通常チャット・cron・記憶統合では公開しない。
TaskExecからの子タスク作成禁止も維持する。

## Animaが行う手順

1. 依頼原文と必要な記録を読み、`list_tasks(detail=true)` で既存作業を確認する。
   一覧が空でも過去の検証が未実施とは限らない。完了済みの成果物も確認する。
2. 応答内で終わる作業は直接実行する。継続が必要な許可済み作業は、
   `submit_tasks` に一意の `batch_id` と `tasks` を渡して実行可能なタスクにする。
   `current_state.md` のメモや追跡用の台帳登録だけで終了しない。
3. タスクには原文、目的、入力・既存成果物、最初の成果物、完了条件、
   制約、初回報告期限、報告先を含める。仕様が未確定なら、資料調査、
   明示した仮定、感度分析の設計から進め、仮定を実運用の確定ルールと混同しない。
4. `status: submitted` と `task_ids` を確認してから受付報告する。
   ID・担当・最初の成果物・初回報告期限を示し、開始未確認なら「登録済み・実行待ち」と書く。
   登録失敗時は実エラーを報告する。使えるツールを試さず「登録できない」と断定しない。
5. 既存の未完タスクは重複登録しない。停止理由が解消した場合だけ、
   同じ `task_id` と `resume:true` で再開する。既に完了した解析に追加の検証を
   依頼された場合は、前の成果物とIDを参照する後続タスクを作る。
6. 元のスレッドへ結果またはブロッカーを報告する。Inboxの最終応答は自動返信されるため、
   同じ受付文を送信ツールで二重投稿しない。TaskExecの後続報告先はタスク本文に明記する。

## 運用者の検証手順

- ツール公開の回帰確認:
  `.venv/Scripts/python.exe -m pytest tests/unit/core/tooling/test_submit_tasks_trigger_gate.py tests/unit/core/tooling/test_tool_surface_matrix.py tests/unit/core/test_mcp_server.py tests/unit/execution/test_sdk_hooks_agent_intercept.py tests/unit/core/test_submit_drain_integration.py -q`
- 既存のAnimaプロセスが旧モジュールを保持している場合、稼働中のタスクがないことを確認してから
  `POST /api/animas/<name>/restart` で対象Animaだけを再起動する。
  サーバー全体の再起動は不要。
- 明示的に許可された依頼をInboxへ届け、activity_logで本人の `submit_tasks` 呼出しと
  `status: submitted` を確認する。運用者が代行登録したタスクでは本人の登録能力の確認にならない。
- `animaworks task show <id> --json` でattemptの `started_at` を確認する。
  `in_progress`、成果物、後続報告をそれぞれ確認し、登録成功と検証完了を混同しない。
- `state/task_queue.jsonl` や `state/pending/` は旧移行証跡。直接編集・再投入しない。

## 2026-10-21の原因

rikaの行動ルールは登録を要求した一方、共有ツールポリシーはInboxで
`submit_tasks` を除外し、Inbox共通プロンプトも使用を禁じていた。
ツール公開と日本語・英語・韓国語の共通プロンプトを揃えて修正した。
CLIの迂回実行を通常手順にはせず、正式なツールで登録する。

実機確認では運用者からrikaのInboxへ依頼原文を渡し、本人の
`submit_tasks` 呼出しと `status: submitted` を2026-10-21 12:23:09 JSTに確認した。
後続IDは `rotation-followup-20261021`、batchは `rika-rotation-20261021`。
task showでも初回attemptの開始を確認済み。前回の運用者による代行登録とは異なり、
今回はInbox応答を担当するrika自身が登録した。Discordの新しいGatewayイベントを
偽装せず、同じInbox処理系への運用者メッセージで確認した。
初回報告期限は登録から60分以内（13:23 JST）。このIDは実際の検証準備作業なので、
動作確認のために同じ作業を再登録しない。
