> 確認したコミット: 581e20f1

# Task Store へのランタイム移行

この手順は、従来のタスク投入データを `shared/taskboard.sqlite3` の永続 Task Store へ移行する際に使用する。新しいランタイムで旧形式の入力が見つかっても、自動で実行対象に混ぜない。移行が必要な担当だけを停止・照合して切り替える。

## 移行前の確認

- 旧コードと新コードを同じデータディレクトリに同時接続しない。
- `animaworks task-store status --anima <name>` で対象 Anima の状態を確認する。
- `animaworks task-store quiesce --anima <name>` で新しい claim を止める。実行中の試行は終了するまで待ち、サーバーと対象 worker を停止する。
- SQLite の backup 出力先を新しいパスに指定し、空き容量とアクセス権を確認する。

## 移行と照合

```sh
ANIMAWORKS_DATA_DIR=/path/to/runtime animaworks task-store status --anima sample
ANIMAWORKS_DATA_DIR=/path/to/runtime animaworks task-store quiesce --anima sample
ANIMAWORKS_DATA_DIR=/path/to/runtime animaworks task-store migrate \
  --anima sample --backup /path/to/backup/before.sqlite3
```

移行処理は入力形式、実行中 lease、競合などを検査してから保存する。異常な行、結果が不明な実行中の仕事、競合した入力があれば停止する。表示されたエラーを解消してから改めて状態を調べる。元ファイルは証跡として保持し、移行が完了したことを理由に削除しない。

移行件数とタスク ID を照合し、指示、制約、model、workspace、依存関係、追跡情報が意図した内容かを確認する。結果が確定していない操作は外部の状態を確認し、自動で再投入しない。手順書、Anima ごとの指示、共有テンプレートに古い投入方法が残っていないかも見直す。

照合が済んだ対象だけ再開する。

```sh
ANIMAWORKS_DATA_DIR=/path/to/runtime animaworks task-store resume --anima sample
```

その後、新しいランタイムを起動して Task Store の状態と実際の処理を確認する。一度に全 Anima を切り替える必要はない。

## タスクの状態と再開

Task Store は task ID と試行 ID を使って claim と更新を管理する。worker が所有する実行中状態を他の実行経路から上書きしない。完了済みまたは取消済みの仕事は同じ ID で再投入せず、別の依頼として新しい ID を使う。未完了の作業を再開する場合は、保存済みの入力を参照し、重複する試行が存在しないことを確認する。

DB の claim は、外部サービスへの副作用が厳密に一度だけ起きることを保証しない。送信や変更の結果が不明な場合は外部の実状態を確認してから判断する。

## 切戻し

完了済みの作業を再実行しないため、古い DB backup をそのまま戻して起動しない。新しいランタイムを停止し、現在の Task Store 状態を別の場所へ export してから、必要な設定・成果物を個別に照合する。切戻し時も旧新プロセスが同じデータディレクトリを同時に使わないようにする。

詳細な CLI オプションと最新の状態は `animaworks task-store --help` および[CLI リファレンス](../reference/cli.md)を確認する。
