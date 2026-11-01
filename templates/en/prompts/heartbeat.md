This is a heartbeat. Please perform your regular periodic check.

## Check Items
{checklist}

Choose the necessary response for unprocessed requests, anomalies, and work with deadlines.
- For actual work, `submit_tasks`; for delegation, `delegate_task`. Link additional information to an existing task to its existing ID, and do not create new work with the same content. For contacting or obtaining approval from humans, use `send_message` / `call_human` to send directly to the party who needs to make a decision or respond, and do not forward the same content to every level of the hierarchy.
- For instructions received, leave either a response, a delegation, or an explicitly stated reason for waiting.
- Use `animaworks-tool task board` to take inventory of your own ledger. Whether to close something is judged by the owner based on the current situation, and takes priority over past designations in the task body such as "no cancellation" or "keep pending." For waits you cannot advance yourself, write the reason for waiting and the condition for removing the wait in `task cancel ID --reason 理由` (if there is a hold ledger, put one line there); for items whose premises have changed or that cannot be started for the time being, close them and consolidate later checks into a single summary task, and for items already concluded, use `task done ID --note 結果`. The delegating side should check with `--all`, and for delegations that are not progressing, close them with `task claim ID` → `task cancel`.
- For notifications of incomplete execution, confirm the completed operations and results before deciding whether to continue; to continue, add `{{"task_id":"既存ID","resume":true}}` to the tasks in `submit_tasks` (the original input is already saved). If unnecessary, use `update_task(status="cancelled", summary="理由")`.

Periodic patrols or bulk resubmission for repair purposes are unnecessary. Refer to the necessary business procedures and approval conditions. If there is nothing to handle, return only HEARTBEAT_OK.

## Confirmation of Observation and Communication

If the Current Pre-Observed Heartbeat Snapshot is presented, confirm it first as the observation result for the fixed scope. Do not rescan the same range; investigate additionally only when external confirmation is necessary. For communication, follow `communication/message-quality-protocol.md`; for delegation, follow `operations/task-delegation-guide.md`.
