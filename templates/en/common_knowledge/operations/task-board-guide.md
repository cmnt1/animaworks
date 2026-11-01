# TaskBoard and Human-Facing Reports

## Source of Truth and Display

The TaskBoard consists of the source-of-truth tasks and display metadata.
Use `list_tasks(detail=true)` / `task_tracker()` to check status.
`state/current_state.md` is the work context, and `state/task_results/` is the trial result; they are not a separate execution ledger.
Display columns and archives do not replace execution results or cancellations.

## Separate task completion from approval and post-processing

A task's done status indicates that the task's request and completion conditions have been met. It is separate from formal approval of Products or permission for production deployment.
If corrections and evidence submission have been accepted, keep that work task as done. If the overall case review, approval, final notification, Inbox organization, or ledger confirmation remains, manage the unconfirmed items and the original task ID in a separate review-owner task. Do not return the original work task to pending on the grounds of these post-processing steps.
Only when redoing the original work itself, explicitly set resume=true. Since saved input does not change, register additional separate work as a new request.

## No Manual Double-Booking

There is no obligation to rewrite `shared/task-board.md` after each delegation, completion, or Heartbeat.
You may create task reports requested by humans, but reference only the necessary scope from the source of truth, and clearly note the creation time and any unconfirmed items.
Do not delete or weekly-reset existing report files without approval. Do not re-submit work based solely on report status.

## External Sharing

Post or update on Slack only when requested by a human or when an existing permitted operation is in place.
Follow the permissions and approval conditions of `slack_channel_post` / `slack_channel_update`, and check company boundaries, confidential scope, and previously posted content.
Do not add automatic new posts or notifications.

## Reading and Writing via CLI

Use `animaworks-tool task board [--anima NAME | --all] [--stale DAYS] [--limit N]` to list incomplete tasks,
and `task show ID` to check details. Use `task claim ID [--ttl 30m]` to acquire a lease,
`task note ID TEXT` to add notes, `task done ID --note TEXT` for completion,
`task cancel ID --reason REASON` for cancellation, and `task release ID` to release the lease.
If JSON is needed, append `--json` to `board` / `show`.

A lease is a time-limited lock for closing or annotating someone else's tasks. You can only modify while holding it, and it expires naturally after the default 30 minutes.
You can modify your own tasks without a lease as long as no one else holds one.
It is the anima that reviews and decides; machines do not close tasks automatically.
The owner's judgment takes precedence over past specifications in the task body, such as "no cancellation" or "keep pending."
When the owner uses `done` / `cancel` on their own task, the delegating anima is automatically notified with the reason. The delegator checks this notification before re-issuing the same work.
