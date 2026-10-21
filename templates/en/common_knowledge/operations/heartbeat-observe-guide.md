# Heartbeat Observe Guide

Heartbeat Observe is a lightweight observation phase for status checks and planning decisions. It does not perform normal actual work, long investigations, arbitrary file exploration, or status checks via shell.

## Principles

- MUST: If `status: ok` has `Current Pre-Observed Heartbeat Snapshot`, use it and do not call tools redundantly. If there is no prior observation, call `heartbeat_observe_snapshot` at the start of Observe as a fallback.
- MUST: For Inbox, task_queue, current_state, and state/pending、state/task_results、background_notifications、peer_activity、recent_own_files, use the results of `heartbeat_observe_snapshot` as the primary basis.
- MUST NOT: Do not use Bash / shell / `rtk proxy` / `Get-Content` / `ls` / `read_file` / `list_directory` for the fixed-scope checks above.
- MUST NOT: Do not use Heartbeat observation values, times, counts, or decision logs as TaskBoard task names. If necessary, attach them to the context / task_results / activity_log of an existing task.
- MUST: Only when `status: ok` cannot be obtained from either prior observation or a direct call, do not repeat the same blocked path; record it as a blocker in `state/current_state.md` or report it as needed.

## Conditions for HEARTBEAT_OK

`HEARTBEAT_OK` applies only when fixed-scope observation via prior observation or a direct call to `heartbeat_observe_snapshot` has been completed, and there are no unprocessed instructions, overdue tasks, unexecuted pending items, unconfirmed task_results, or blockers that should be reported.

## Additional Checks

Only when it is necessary to check external services, Board, Slack, GitHub, Web, etc. outside the snapshot, use the relevant dedicated tool. Do not use shell as a substitute for the fixed scope.
