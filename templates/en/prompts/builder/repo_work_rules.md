### Repository Work Rules

- Treat the canonical `main` / `master` checkout as read-only. Implement, verify, and commit only in a dedicated `git worktree`
- Put disposable work (clones, build outputs, validation logs, temporary scripts) under `ANIMAWORKS_SCRATCH_DIR`; keep work directories out of `state/`. Scratch is removed when a task ends or after 24 hours of inactivity
- Put only worktrees shared with other Anima under `{data_dir}/companies/<company>/shared/worktrees/`, then remove them with `git worktree remove` when finished. Put private worktrees under scratch; worktrees untouched for 24 hours are removed automatically. Operations on the canonical checkout are limited to `git worktree add` and reading
- Use the configured shared package caches (`UV_CACHE_DIR`, etc.) instead of creating a cache directory for each PR
- Merge from a worktree only after confirming that the canonical checkout is clean. If it is dirty, make no changes and report it
- Never stash, discard, or overwrite another actor's changes without explicit instruction
