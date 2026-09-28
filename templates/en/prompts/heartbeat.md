This is a heartbeat. Please perform the periodic check for your area of responsibility.

## Items to Check
{checklist}

Select the necessary action for unprocessed requests, anomalies, and tasks with deadlines.
- For actual work, use `submit_tasks`; for delegation, use `delegate_task`. Attach additional information to existing task IDs, and do not create new tasks for the same content. For human contact or approvals, send directly via `send_message` / `call_human` to those who need to decide or respond, and do not forward the same content to the entire hierarchy.
- For any instruction received, leave either a response, a delegation, or an explicit reason for waiting.
- Use `animaworks-tool task board` to take stock of your own ledger. Whether to close an item is decided by the owner based on the current situation, taking priority over past notes in the task text such as "no cancellation" or "keep pending." For waits you cannot progress yourself, write the reason for waiting and the condition for removing it, then add one line to `task cancel ID --reason 理由` (or to the hold ledger if one exists). Close items whose premises have changed or that cannot be started for the time being, and consolidate later checks into a single summary task. For items already concluded, use `task done ID --note 結果`. The delegating side should check via `--all`, and for delegations that are not progressing, close them via `task claim ID` → `task cancel`.
- For notifications of incomplete execution, confirm completed operations and results before deciding whether to continue; if continuing, add `{{"task_id":"既存ID","resume":true}}` to the tasks in `submit_tasks` (the original input is already saved). If not needed, use `update_task(status="cancelled", summary="理由")`.

No need for repair-purpose sweeps or batch re-submission. Refer to required business procedures and approval conditions as needed. If there is nothing to address, return only HEARTBEAT_OK.
