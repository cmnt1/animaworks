# TaskBoard and human-facing reports

## Authority and presentation

TaskBoard projects canonical tasks together with presentation metadata.
Use `list_tasks(detail=true)` / `task_tracker()` for state.
`state/current_state.md` is working context and `state/task_results/` holds attempt results,
not independent execution ledgers. Columns, snooze, and archive do not substitute for task outcomes
or cancellation.

## Avoid duplicate manual tracking

There is no requirement to rewrite `shared/task-board.md` after every delegation, completion, or
heartbeat. Produce a report when a human requests one, using the relevant canonical state and noting
its timestamp and uncertainties. Do not delete or weekly-reset existing reports without authorization.
A report's state must not republish a task.

## External sharing

Post or update Slack only when requested or covered by an existing authorized workflow.
Respect `slack_channel_post` / `slack_channel_update` permissions and approval conditions;
check company boundaries, confidentiality, and previous posts. Do not add automatic posts or alerts.

## CLI reads and writes

Use `animaworks-tool task board [--anima NAME | --all] [--stale DAYS] [--limit N]` to list active tasks,
and `task show ID` to inspect one. Use `task claim ID [--ttl 30m]` to acquire a lease,
`task note ID TEXT` to append a note, `task done ID --note TEXT` to complete, `task cancel ID --reason REASON`
to cancel, and `task release ID` to release the lease. Add `--json` to `board` or `show` for machine-readable output.

A lease is a time-limited lock that authorizes its holder to close or annotate someone else's task.
Changes are allowed only while the lease is held; by default it expires naturally after 30 minutes.
An owner may change their own task without a lease when nobody else holds one.
Anima makes the judgment; machines do not close tasks automatically.
The owner's current judgment takes precedence over earlier notes in the task such as "do not cancel" or "keep pending".
When owners `done` / `cancel` their own task, the delegating anima is notified with the reason. Delegators read that notice before re-sending the same work.
