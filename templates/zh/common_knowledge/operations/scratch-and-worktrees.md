# 工作物的放置位置（scratch・共享 worktree・缓存）

一次性工作物与需要保留之物的放置位置。

## 放置位置

| 用途 | 放置位置 |
|---|---|
| 仅自己使用的 worktree・clone・构建・验证日志・临时脚本 | `$ANIMAWORKS_SCRATCH_DIR` |
| 交给其他 Anima 进行评审・验证的 worktree | `{data_dir}/companies/<company>/shared/worktrees/` |
| 日后回看的手顺・脚本 | 自己的 `procedures/` |
| 日后回看的证据（报告・截图・汇总） | `shared/evidence/` 或 PR 评论 |
| `state/` | 仅常设的状态文件（`current_state.md`・`background_tasks/` 等） |

`$ANIMAWORKS_SCRATCH_DIR` 会在每次执行时自动准备。任务执行中指向 `animas/<self>/scratch/task-<task_id>/`，其他情况（chat・heartbeat・inbox・cron）指向 `animas/<self>/scratch/<type>/`。

```bash
WT="$ANIMAWORKS_SCRATCH_DIR/myrepo"
git -C /path/to/canonical worktree add --detach "$WT" origin/main
TMP="$(mktemp -d -p "$ANIMAWORKS_SCRATCH_DIR")"
```

## 自动删除

自动删除仅在可以追踪进程使用情况的 Linux 上运行。Windows 不会在任务结束时删除 scratch，也不会执行定期清理。`workspace_sweep_enabled=false` 同时关闭每小时和每日定期清理。

- 在支持自动清理的 Linux 上，任务完成或取消时删除任务 scratch，并从父仓库移除其中的 worktree 注册。
- 24 小时未使用的 scratch 会被清理；正在使用的目录会保留。
- `shared/worktrees/` 中，仅清理超过 24 小时未使用且没有未提交变更的 linked worktree，通过 Git 删除。存在未提交变更、独立 clone 或无法检查 Git 状态的仓库会保留。
- 在自动清理启用的 Linux 上，不需要在作业结束时手动删除临时目录。需要长期保留的成果请移到上表的位置。

## 包缓存

`UV_CACHE_DIR`・`PIP_CACHE_DIR`・`npm_config_cache`・`npm_config_store_dir`（pnpm）・`GRADLE_USER_HOME`・`NUGET_PACKAGES`・`COMPOSER_CACHE_DIR` 已自动配置为指向共用的 `{data_dir}/cache/<type>`。直接使用即可。
