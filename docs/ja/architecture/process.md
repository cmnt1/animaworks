> 確認したコミット: b304b7dc

# プロセス構成と通信

実行時は phase3 のプロセス構成を前提とする。server は API と WebSocket を提供し、同じ server 内の Process Supervisor が Anima root process を管理する。root は scheduler と制御用 IPC を持ち、会話や背景処理を分離した task runner に渡す。

```mermaid
flowchart LR
    Server[server / Process Supervisor] -->|起動・監視| Root[Anima root]
    Server <-->|制御 IPC| Root
    Root -->|IPC v2 の要求| Runner[task runner]
    Runner -->|進捗・結果| Root
    Runner -->|HTTP の記憶 URL| Memory[記憶サービス]
```

## 起動と IPC

`server/supervisor/manager.py` が root process を起動し、`core/runtime/runner.py` が Anima の実行時オブジェクトと各サービスを初期化する。`core/runtime/task_runner_supervisor.py` は依頼ごとに独立した task runner を起動し、heartbeat、cron、inbox、チャット、greet、background task などを分離して実行する。

root と server の制御通信は `core/runtime/ipc.py` を通る。`core/runtime/ipc_v2.py` は root と task runner の要求・応答を扱い、`core/runtime/transport.py` が接続方式を選ぶ。通常は Unix domain socket を使い、Windows では loopback TCP を使う。Unix socket のパスが OS の長さ上限を超える場合も loopback TCP に切り替える。

ベクトル検索に必要な接続先は server が起動時に URL として用意し、task runner に渡す。root が記憶データへのアクセスを管理し、子プロセスからはサービス経由で検索する。検索経路の詳細は `docs/ja/memory/retrieval.md` を参照する。

## 起動準備と readiness

server は起動直後に全 API を利用可能とはせず、RAG の preflight と Anima process の起動を進める。準備中は startup progress を更新し、readiness gate が進捗画面を返す。Anima root は IPC endpoint の作成後も初期化を続け、ping が ready を返してから supervisor の確認を受ける。起動時の重い準備と依存サービスの初期化が終わるまで、公開 readiness は ready にならない。

## 異常終了と再起動

`server/supervisor/restart_state.py` の状態機械が Anima ごとの連続失敗回数、次回再起動時刻、最終エラーを一元管理する。規定回数の失敗後は UI に FAILED を表示するが、自動復旧は継続する。再起動間隔は指数バックオフで延長され、上限は 30 分である。安定稼働が続けば失敗回数をリセットする。

エンジンのイベント idle timeout は engine event が 1200 秒間届かない場合に適用される。これは会話全体の実行時間上限ではない。task runner の停止・応答監視は root 側の supervisor が担う。
