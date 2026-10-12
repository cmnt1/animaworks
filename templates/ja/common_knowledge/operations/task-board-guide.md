# タスクボードと人間向け報告

## 正本と表示

TaskBoard は正本のタスクと表示用metadataから構成される。
状態確認は `list_tasks(detail=true)` / `task_tracker()` を使う。
`state/current_state.md` は作業文脈、`state/task_results/` は試行結果であり、別の実行台帳ではない。
表示列・archiveは実行結果や取消の代わりにならない。

## 作業完了と承認・後処理を分ける

タスクの done は、そのタスクの依頼と完了条件を満たしたことを表す。Products の正式承認や本番適用の許可とは別である。
修正・証跡提出が検収済みなら、その作業タスクは done のままにする。案件全体のレビュー、承認、最終通知、Inbox整理、台帳確認が残る場合は、レビュー担当の別タスクで未確認事項と元タスクIDを管理する。これらの後処理を理由に元の作業タスクを pending に戻さない。
元の作業自体をやり直す場合のみ resume=true を明示する。保存済み入力は変わらないため、追加の別作業は新しい依頼として登録する。

## 手書きの二重管理をしない

各委譲・完了・Heartbeatのたびに `shared/task-board.md` を書き直す義務はない。
人間が要望した案件報告は作ってよいが、正本から必要な範囲を参照し、作成時刻と未確認事項を明記する。
既存の報告ファイルは承認なく削除・週次リセットしない。報告の状態だけで仕事を再投入しない。

## 外部共有

Slackの投稿・更新は人間の依頼または既存の許可された運用がある場合のみ行う。
`slack_channel_post` / `slack_channel_update` の権限と承認条件を守り、
会社境界・機密範囲・既済の投稿を確認する。自動的な新規投稿や通知を増やさない。

## CLI での読み書き

`animaworks-tool task board [--anima NAME | --all] [--stale DAYS] [--limit N]` で未完了タスクを一覧し、
`task show ID` で詳細を確認します。`task claim ID [--ttl 30m]` で lease を取得し、
`task note ID TEXT` で注記、`task done ID --note TEXT` で完了、
`task cancel ID --reason REASON` で取消、`task release ID` で lease を解放します。
JSON が必要な場合は `board` / `show` に `--json` を付けます。

lease は他人のタスクを閉じたり注記したりするための期限付きロックです。取得中だけ変更でき、既定の30分で自然に切れます。
自分のタスクは他の人の lease が無ければ lease なしでも変更できます。
見て判断するのは anima であり、機械はタスクを自動で閉じません。
持ち主の判断は、タスク本文にある「取消なし」「pending維持」等の過去の指定より優先します。
持ち主が自分のタスクを `done` / `cancel` すると、委譲元の anima へ理由付きで自動通知されます。委譲元は同じ仕事を出し直す前にこの通知を見ます。
