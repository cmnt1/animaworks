# Heartbeat Observe Guide

Heartbeat Observe is a lightweight observation phase for status checks and planning. Do not perform hands-on work, long research, arbitrary file exploration, or shell-based state inspection during normal Heartbeat.

## Rules

- MUST: Call `heartbeat_observe_snapshot` first during Observe.
- MUST: Use `heartbeat_observe_snapshot` as primary evidence for Inbox, task_queue, current_state, state/pending, state/task_results, background_notifications, peer_activity, and recent_own_files.
- MUST NOT: Use Bash / shell / `rtk proxy` / `Get-Content` / `ls` / `read_file` / `list_directory` to inspect those fixed locations.
- MUST NOT: Put Heartbeat observation values, timestamps, counts, or decision logs into TaskBoard task titles. Use existing task context / task_results / activity_log when a record is needed.
- MUST: If the snapshot tool is unavailable or returns an error, do not repeat the same blocked path. Record the blocker in `state/current_state.md` or report it when appropriate.

## HEARTBEAT_OK Gate

Return `HEARTBEAT_OK` only after fixed-scope observation via `heartbeat_observe_snapshot` is complete and there are no unhandled instructions, STALE/OVERDUE tasks, unexecuted pending items, unchecked task_results, or blockers that require reporting.

## Additional Checks

Use a dedicated tool only when you must inspect something outside the snapshot scope, such as an external service, Board, Slack, GitHub, or the web. Do not use shell as a substitute for fixed-scope snapshot observation.
