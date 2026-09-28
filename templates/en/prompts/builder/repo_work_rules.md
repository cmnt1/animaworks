### Repository Working Rules

- The canonical checkout's `main` / `master` are read-only. Implementation, validation, and commits must always be done in a dedicated `git worktree`
- Worktrees should be created in `{data_dir}/companies/<会社>/shared/worktrees/` (a location shareable with other anima; repositories that produce `node_modules` or build artifacts must be here) or `/tmp/`. Operations on the canonical checkout are limited to `git worktree add` and reference
- Merges from a worktree should only be performed after confirming the canonical checkout is clean. If it is dirty, report it without making changes
- Do not arbitrarily stash, discard, or overwrite others' changes
