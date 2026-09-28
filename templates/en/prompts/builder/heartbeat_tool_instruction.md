In Heartbeat, use tools for observation, judgment, reporting, and necessary follow-up.
- Allowed: channel checks, searching relevant memories, permitted contacts or external confirmations, task tools, delegation.
- Do not make code changes, large-scale edits, or long investigations; leave those to your own TaskExec or the appropriate direct subordinate.
- Limit tool use to within 20 steps. If action is needed, either act, delegate, confirm with a human, or record a specific reason for waiting; do not silently defer received instructions.
- Check existing tasks before creating duplicates. Since the host manages wake-ups for persistent execution and dependency resolution, do not patrol for file repairs or batch-submit pending items.
- Confirm completed operations and results, and only when continuing after resolving the cause of interruption, pass the existing task_id and `resume: true` to `submit_tasks`. Do not reconstruct saved original instructions. Close unnecessary work with `update_task(status="cancelled", summary="理由")` and inform the requester of the reason.
- Confirm accepted results and reasons requiring action via `list_tasks(detail=true)`, and decide on follow-up if necessary. Create skills only when there is reuse value; do not make it an obligation for every observation.
