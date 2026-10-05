# Heartbeat: {name}

## Active Hours
24 hours (server configuration timezone)

## Current Time
Use the value of the `現在時刻` field in the system prompt. Do not infer from history or schedules.

## Observation Rules
- If a `Current Pre-Observed Heartbeat Snapshot` with `status: ok` is present, use it as evidence for Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files and do not call the tool again; otherwise call `heartbeat_observe_snapshot` as the fallback
- During normal Heartbeat, do not use shell / `rtk proxy` / `Get-Content` / `ls` to inspect those fixed locations
- Only if neither snapshot path returns `status: ok`, do not repeat the same blocked path; record or report the blocker

## Checklist
- Are there unread messages in the Inbox?
- Have any blockers occurred in ongoing tasks?
- Have new files been placed in my workspace?
- If nothing, do nothing (HEARTBEAT_OK)

## Notification Rules
- Notify relevant parties only when deemed urgent
- Do not repeat the same notification within 24 hours
