### Task Recording in Chat

- Do not use `submit_tasks` in normal chat
- If a human gives explicit completion criteria for work that can outlive one conversation stream, register it with `backlog_task` before starting (it is registered as `pending`; call `update_task(status="in_progress")` only while you are actually working on it in this conversation). A conversation ending or an interim report must not complete or remove it; keep it durable until the completion criteria are proven, the task is explicitly blocked, or the human cancels it
- Set `done` only after verifying evidence for every completion criterion
