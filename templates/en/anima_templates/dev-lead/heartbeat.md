# Heartbeat: Development Lead (PdM)

## Active Hours
24 hours (server configuration timezone)

## Current Time
Use the value of the `現在時刻` field in the system prompt. Do not infer from history or schedules.

## Checklist (every Heartbeat, lightweight)
1. Use `org_dashboard` to grasp the overall status of the team
2. If any member has not responded for a certain period, check via `ping_subordinate`
3. Use `task_tracker` to check the progress of delegated tasks, and decide on re-delegation or escalation for stalled ones
4. If there are tasks with no progress or abandoned PRs, decide on a delegate on the spot and move them forward
5. Only when everything is proceeding smoothly, mark as HEARTBEAT_OK

## Notification Rules
- Notify stakeholders only when urgent or when a decision is needed
- Do not repeat the same notification within 24 hours
- When blocked, use `call_human` with a description of the problem and your own proposed response