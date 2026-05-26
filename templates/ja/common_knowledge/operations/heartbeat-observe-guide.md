# Heartbeat Observe Guide

Heartbeat Observe は、状態確認と計画判断のための軽量な観測フェーズです。通常の実作業、長い調査、任意ファイル探索、shell による状態確認は行いません。

## 原則

- MUST: Observe の最初に `heartbeat_observe_snapshot` を呼ぶ。
- MUST: Inbox、task_queue、current_state、state/pending、state/task_results、background_notifications、peer_activity、recent_own_files は `heartbeat_observe_snapshot` の結果を一次根拠にする。
- MUST NOT: 上記の固定スコープ確認のために Bash / shell / `rtk proxy` / `Get-Content` / `ls` / `read_file` / `list_directory` を使わない。
- MUST NOT: Heartbeat の観測値、時刻、件数、判断ログを TaskBoard のタスク名にしない。必要なら既存タスクの context / task_results / activity_log に寄せる。
- MUST: snapshot が使えない、または error を返す場合は、同じ blocked 経路を繰り返さず、ブロッカーとして `state/current_state.md` に記録するか、必要に応じて報告する。

## HEARTBEAT_OK の条件

`HEARTBEAT_OK` は、`heartbeat_observe_snapshot` による固定スコープ観測を完了し、未処理指示、STALE/OVERDUEタスク、未実行pending、未確認task_results、報告すべきブロッカーがない場合に限る。

## 追加確認

snapshot の外にある外部サービス、Board、Slack、GitHub、Web等を確認する必要がある場合だけ、該当する専用ツールを使う。固定スコープの代替として shell を使ってはいけない。
