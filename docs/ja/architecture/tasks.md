> 確認したコミット: b304b7dc

# タスク管理

タスクの正本は `shared/taskboard.sqlite3` に置く TaskStore である。`core/tasks/board/` は canonical task、alias、attempt、lease を読み書きし、CLI と Web UI に同じタスク情報を提供する。別の表示用カード層は持たない。

## 状態と実行記録

通常の状態は `pending`、`in_progress`、`delegated`、`done`、`cancelled` である。委任された側の実タスクを TaskStore に保存し、委任元には alias row を作るため、同じ作業を二重に数えずに追跡できる。Web Task Board は TODO、RUNNING、WAITING、DONE の列に投影し、人間から登録されたタスクを各列内で先に表示する。

実行を開始すると task attempt が作られ、固有 token と通番で実行主体を識別する。古い attempt からの更新は拒否され、結果や停止理由は attempt 履歴に残る。task lease は actor が一定期間タスクを操作する権利を確保する仕組みで、完了・取消時には解放される。未完了の実行を再開させる通知は wake-up outbox に永続化され、処理後に確認済みとなる。

TaskStore の schema と実装は `core/tasks/board/tasks.py`、一覧の投影は `view.py` にある。`state/task_queue.jsonl` は既存データの明示的な取り込みに関わるファイルであり、実行時の正本ではない。

## CLI、委任、background task

`animaworks task board` はボード一覧、`list` と `show` はタスク情報、`add` は新規登録に使う。`claim` と `release` は lease を取得・解放し、`done`、`cancel`、`note` は結果や理由の記録に使う。`update` は状態変更、`resume` は保存済み入力での再投入を行う。各引数と他の CLI は[CLI リファレンス](../reference/cli.md)を参照する。

Anima から別の Anima へ仕事を渡す場合は `delegate_task` を使う。委任先の実行結果は alias からたどれる。時間のかかる `animaworks-tool` 操作は `submit` で別 background task として起動でき、その状態・結果は `state/background_tasks/` に保存される。完了時は依頼元へ通知される。引数の一覧は[ツール CLI リファレンス](../reference/tool-cli.md)を参照する。

外部タスク collector は GitHub、Slack、Chatwork、Gmail などの連携先からタスク候補を収集し、source 別の状態とともに snapshot として提供する。これは Anima の実行 TaskStore とは別の読み取り用データである。
