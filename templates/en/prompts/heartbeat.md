Heartbeat: perform the scheduled checks assigned to your role.

## Checks
{checklist}

When a `Current Pre-Observed Heartbeat Snapshot` with `status: ok` is present, use it as primary evidence and do not call the tool again. Only call `heartbeat_observe_snapshot` as a fallback when the pre-observed snapshot is absent.
Do not re-read the fixed scope with shell / `rtk proxy` / `read_file` / `list_directory`.

Choose necessary actions for unanswered requests, anomalies, or time-sensitive work.
- Use `submit_tasks` for your execution and `delegate_task` for delegation. Attach additional context to an existing task ID instead of duplicating work. Use `send_message` / `call_human` for contact or approval; do not relay the same content through every layer.
- Handle requests, delegate, or leave an explicit waiting reason and condition.
- Take stock of your ledger with `animaworks-tool task board`. The owner decides whether to close based on the current situation, and this overrides past notes in the task body such as "do not cancel" or "keep pending". Close waits you cannot advance yourself with `task cancel ID --reason REASON` stating the wait and its release condition (add a line to the hold ledger if your org has one); close tasks whose premise changed or that you cannot start soon, gathering later checks into one aggregate task; close concluded ones with `task done ID --note RESULT`. If you delegate, look with `--all` and close stalled delegations with `task claim ID` → `task cancel`.
- For an incomplete-run notice, check what was already done before deciding to continue; to continue, use `submit_tasks` with `{{"task_id":"existing-id","resume":true}}` (the original input is saved). If no longer needed, `update_task(status="cancelled", summary="reason")`.

No need to poll for repair or resubmit all pending work. Consult procedures and approval requirements as needed. If nothing needs attention, return only HEARTBEAT_OK.
