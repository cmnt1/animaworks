# タスクボードと人間向け報告

## 正本と表示

TaskBoard は正本のタスクと表示用metadataから構成される。
状態確認は `list_tasks(detail=true)` / `task_tracker()` を使う。
`state/current_state.md` は作業文脈、`state/task_results/` は試行結果であり、別の実行台帳ではない。
表示列・snooze・archiveは実行結果や取消の代わりにならない。

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
