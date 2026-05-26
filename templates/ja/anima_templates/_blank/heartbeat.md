# Heartbeat: {name}

## 活動時間
24時間（サーバー設定タイムゾーン）

## 現在時刻
システムプロンプトの `現在時刻` フィールドの値を使うこと。履歴やスケジュールから推測しない。

## 観察ルール
- 最初に `heartbeat_observe_snapshot` を呼び、Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files の確認根拠にする
- 通常のHeartbeatでは、上記固定スコープ確認のために shell / `rtk proxy` / `Get-Content` / `ls` を使わない
- snapshot が使えない場合は同じ blocked 経路を繰り返さず、ブロッカーとして記録または報告する

## チェックリスト
- Inboxに未読メッセージがあるか
- 進行中タスクにブロッカーが発生していないか
- 自分の作業領域に新しいファイルが置かれていないか
- 何もなければ何もしない（HEARTBEAT_OK）

## 通知ルール
- 緊急と判断した場合のみ関係者に通知
- 同じ内容の通知は24時間以内に繰り返さない
