# Heartbeat: {name}

## Active Hours
24 hours (server timezone)

## Current Time
Use the value from the current time field in the system prompt. Do not infer from history or schedule.

## Observation Rules
- First call `heartbeat_observe_snapshot` and use it as evidence for Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files
- During normal Heartbeat, do not use shell / `rtk proxy` / `Get-Content` / `ls` to inspect those fixed locations
- If the snapshot is unavailable, do not repeat the same blocked path; record or report the blocker

## Checklist
- Are there unread messages in Inbox?
- Are there blockers in ongoing tasks?
- Have any new files been placed in my workspace?
- If nothing, do nothing (HEARTBEAT_OK)

## Notification Rules
- Only notify stakeholders when deemed urgent
- Do not repeat the same notification within 24 hours
