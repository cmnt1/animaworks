# TaskBoard and human-facing reporting

## Source of truth and display

TaskBoard consists of the source-of-truth tasks and display metadata.
Use `list_tasks(detail=true)` / `task_tracker()` to check status.
`state/current_state.md` is the work context, and `state/task_results/` is the trial result; they are not a separate execution ledger.
Display columns and archive do not substitute for execution results or cancellation.

## Separate work completion from approval and post-processing

A task's done indicates that the request and completion conditions for that task have been met. It is separate from formal approval of Products or permission for production deployment.
If the revision or evidence submission has passed acceptance, keep that work task as done. If overall case review, approval, final notification, Inbox cleanup, or ledger confirmation remains, manage the unconfirmed items and the original task ID in a separate review-owner task. Do not return the original work task to pending because of these post-processing steps.
Only explicitly set resume=true when redoing the original work itself. Since saved input does not change, register additional separate work as a new request.

## Do not maintain handwritten duplicate records

There is no obligation to rewrite `shared/task-board.md` on every delegation, completion, or Heartbeat.
You may create case reports requested by humans, but reference only the necessary scope from the source of truth and clearly state the creation time and unconfirmed items.
Do not delete or weekly-reset existing report files without approval. Do not re-inject work based solely on the report's status.

## External sharing

Post or update on Slack only when requested by a human or when there is an existing permitted operation.
Follow the permission and approval conditions of `slack_channel_post` / `slack_channel_update`,
and check company boundaries, confidentiality scope, and existing posts. Do not increase automatic new posts or notifications.

## Reading and writing via CLI

List incomplete tasks with `animaworks-tool task board [--anima NAME | --all] [--stale DAYS] [--limit N]`,
and check details with `task show ID`. Acquire a lease with `task claim ID [--ttl 30m]`,
add notes with `task note ID TEXT`, complete with `task done ID --note TEXT`,
cancel with `task cancel ID --reason REASON`, and release the lease with `task release ID`.
If JSON is needed, add `--json` to `board` / `show`.

A lease is a time-limited lock for closing or annotating someone else's task. Changes are possible only while it is held, and it naturally expires after the default 30 minutes.
Your own tasks can be changed without a lease if no one else holds a lease on them.
It is anima that looks and decides; the machine does not automatically close tasks.
The owner's judgment takes precedence over past instructions in the task body such as "no cancellation" or "keep pending."
When the owner performs `done` / `cancel` on their own task, the delegating anima is automatically notified with the reason. The delegator checks this notification before reissuing the same work.
