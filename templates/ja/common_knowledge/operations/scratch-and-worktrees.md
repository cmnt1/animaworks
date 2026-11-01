# 作業物の置き場所（scratch・共有 worktree・キャッシュ）

使い捨ての作業物と、残すものの置き場所。

## 置き場所

| 用途 | 置き場 |
|---|---|
| 自分だけで使う worktree・clone・ビルド・検証ログ・一時スクリプト | `$ANIMAWORKS_SCRATCH_DIR` |
| 他の Anima にレビュー・検証を引き継ぐ worktree | `{data_dir}/companies/<company>/shared/worktrees/` |
| 後で読み返す手順・スクリプト | 自分の `procedures/` |
| 後で読み返す証跡（レポート・スクリーンショット・集計） | `shared/evidence/` か PR コメント |
| `state/` | 常設の状態ファイル（`current_state.md`・`background_tasks/` など）だけ |

`$ANIMAWORKS_SCRATCH_DIR` は実行ごとに自動で用意される。タスク実行中は `animas/<self>/scratch/task-<task_id>/`、それ以外（chat・heartbeat・inbox・cron）は `animas/<self>/scratch/<type>/` を指す。

```bash
WT="$ANIMAWORKS_SCRATCH_DIR/myrepo"
git -C /path/to/canonical worktree add --detach "$WT" origin/main
TMP="$(mktemp -d -p "$ANIMAWORKS_SCRATCH_DIR")"
```

## 自動削除

- タスク用の scratch は、タスクが完了・キャンセルした時点で消える。中に作った worktree の登録も親リポジトリから外れる。
- scratch は 24 時間触られなければ消える。
- `shared/worktrees/` は 24 時間触られなければ、未コミット変更があっても消える（使用中のものは残る）。
- 後片付けは自動で行われるので、作業の最後に削除コマンドを打つ必要はない。残したいものは上の表の「後で読み返す」行の場所へ移す。

## パッケージキャッシュ

`UV_CACHE_DIR`・`PIP_CACHE_DIR`・`npm_config_cache`・`npm_config_store_dir`（pnpm）・`GRADLE_USER_HOME`・`NUGET_PACKAGES`・`COMPOSER_CACHE_DIR` は、共用の `{data_dir}/cache/<type>` を指すよう自動で設定されている。そのまま使う。
