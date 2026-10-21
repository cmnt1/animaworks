# Heartbeat: {name}

## Active hours
24 hours (server configuration timezone)

## Current time
Use the value of the `現在時刻` field in the system prompt. Do not infer it from history or schedules.

## Observation rules
- If there is a `Current Pre-Observed Heartbeat Snapshot` for `status: ok`, do not stack tool calls to verify Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files. If there is no prior observation, call `heartbeat_observe_snapshot` as a fallback
- During a normal Heartbeat, do not use shell / `rtk proxy` / `Get-Content` / `ls` to check the fixed scopes above
- Only when `status: ok` cannot be obtained from either snapshot path, do not repeat the same blocked path; record or report it as a blocker

## Checklist
- Are there unread messages in the Inbox?
- Has a blocker occurred in an in-progress task?
- Has a new file been placed in your work area?
- If there is nothing, do nothing (HEARTBEAT_OK)

## Notification rules
- If judged urgent, notify the relevant parties
- If there is no supervisor, convey only the key points of deliverables received from subordinates to the user via call_human
- Do not repeat notifications with the same content within 24 hours
