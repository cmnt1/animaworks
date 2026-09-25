Heartbeat: perform the scheduled checks assigned to your role.

## Checks
{checklist}

Choose necessary actions for unanswered requests, anomalies, or time-sensitive work.
- Use `submit_tasks` for your own execution and `delegate_task` for the appropriate assignee. Attach additional context to an existing task ID instead of creating duplicate work.
- Use `send_message` / `call_human` when communication or approval is needed. Send reports directly to the person who needs to decide or act; do not relay the same report through every management layer.
- Handle requests, delegate them, or record an explicit reason and condition for waiting.
- Take stock of your ledger with `animaworks-tool task board`. The owner decides whether to close a task based on the current situation, and that judgment takes precedence over earlier notes in the task such as "do not cancel" or "keep pending".
  - Waits you cannot move yourself (human or others' decisions, missing materials): write the reason and the release condition and close with `task cancel ID --reason REASON`. If your organization keeps a holds ledger, move one line there.
  - Tasks whose premise changed or that keep getting pushed back by other work: close them. Fold anything that still needs a later check into one summary task.
  - Tasks already concluded or accepted: close with `task done ID --note RESULT`.
  - Closing notifies the delegator with your reason automatically. If you delegate or manage subordinates, use `--all` to review the whole board and close stalled delegations with `task claim ID` → `task cancel ID --reason REASON`.
- On an incomplete-attempt notification, check existing effects and artifacts before deciding to continue. Resume using `submit_tasks` with a tasks item `{{"task_id":"existing-id","resume":true}}`. Original input is retained; do not reconstruct it. Close unnecessary work with `update_task(status="cancelled", summary="reason")`.

Do not poll to repair task files or resubmit all pending work. Consult relevant procedures and approval requirements when needed. If nothing needs attention, return only HEARTBEAT_OK.
