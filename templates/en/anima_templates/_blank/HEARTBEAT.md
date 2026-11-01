# Heartbeat: {name}

## Active Hours
24 hours (server-configured time zone)

## Current Time
Use the value of the `現在時刻` field in the system prompt. Do not infer it from history or schedules.

## Observation Rules
- If a `Current Pre-Observed Heartbeat Snapshot` with `status: ok` is present, use it as evidence for Inbox / task_queue / current_state / state/pending / state/task_results / background_notifications / peer_activity / recent_own_files and do not call the tool again; otherwise call `heartbeat_observe_snapshot` as the fallback
- During normal Heartbeat, do not use shell / `rtk proxy` / `Get-Content` / `ls` to inspect those fixed locations
- Only if neither snapshot path returns `status: ok`, do not repeat the same blocked path; record or report the blocker

## Checklist
- Check whether there are unread messages in the Inbox
- Check whether any blockers have arisen for in-progress tasks
- Check whether any new files have been placed in your workspace
- If there is nothing, do nothing (HEARTBEAT_OK)

## Notification Rules
- If something is deemed urgent, notify the relevant parties
- If there is no supervisor, report only the key points of deliverables received from subordinates to the user via call_human
- Do not repeat notifications about the same content within 24 hours
