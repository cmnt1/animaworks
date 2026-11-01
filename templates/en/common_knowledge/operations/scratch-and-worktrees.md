# Where to Put Work Products (Scratch, Shared Worktrees, Caches)

Where to put disposable work products and things you want to keep.

## Locations

| Purpose | Location |
|---|---|
| Worktrees, clones, builds, validation logs, and temporary scripts for your own use | `$ANIMAWORKS_SCRATCH_DIR` |
| Worktrees to hand off to other Anima for review or validation | `{data_dir}/companies/<company>/shared/worktrees/` |
| Procedures and scripts to refer back to later | Your own `procedures/` |
| Evidence to refer back to later (reports, screenshots, summaries) | `shared/evidence/` or PR comments |
| `state/` | Permanent status files only (such as `current_state.md` and `background_tasks/`) |

`$ANIMAWORKS_SCRATCH_DIR` is set up automatically for each run. During task execution, it points to `animas/<self>/scratch/task-<task_id>/`; otherwise (chat, heartbeat, inbox, cron), it points to `animas/<self>/scratch/<type>/`.

```bash
WT="$ANIMAWORKS_SCRATCH_DIR/myrepo"
git -C /path/to/canonical worktree add --detach "$WT" origin/main
TMP="$(mktemp -d -p "$ANIMAWORKS_SCRATCH_DIR")"
```

## Automatic deletion

Automatic deletion is performed only on Linux, where process usage can be tracked. On Windows, scratch deletion at task termination and periodic cleanup are not performed. `workspace_sweep_enabled=false` applies to both hourly and daily periodic cleanup.

- Scratch for a task disappears when the task completes or is canceled. The registration of worktrees created inside it is also removed from the parent repository.
- Scratch disappears if it is not touched for 24 hours.
- In `shared/worktrees/`, only clean linked worktrees that have not been used for 24 hours or more are deleted via Git. Uncommitted changes, standalone clones, and repositories whose Git status cannot be confirmed are retained.
- On Linux with automatic deletion enabled, there is no need to run a deletion command at the end of work. Move anything you want to keep to the location in the "Read later" row of the table above.

## Package caches

`UV_CACHE_DIR`, `PIP_CACHE_DIR`, `npm_config_cache`, `npm_config_store_dir` (pnpm), `GRADLE_USER_HOME`, `NUGET_PACKAGES`, and `COMPOSER_CACHE_DIR` are automatically configured to point to the shared `{data_dir}/cache/<type>`. Use them as is.
