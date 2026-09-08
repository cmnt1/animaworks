### Task Recording in Heartbeat

- Read continuing tasks as `pending` and submit them with `submit_tasks` under the same task_id to continue the already-approved scope. Set `done` only after verifying evidence for every completion criterion
- Record delegation between Anima in the task queue and update relay_chain
- When a task is complete, update status via `update_task`
