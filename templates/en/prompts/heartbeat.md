This is a Heartbeat. Follow the process below.

## Observe
**First call `heartbeat_observe_snapshot` and use it as the primary evidence for fixed-scope observation.**

- Treat `heartbeat_observe_snapshot` as the evidence source for Inbox, task_queue, current_state, state/pending, state/task_results, background_notifications, peer_activity, and recent_own_files.
- During normal Heartbeat Observe, do not use Bash / shell / `rtk proxy` / `Get-Content` / `ls` / `read_file` / `list_directory` to inspect those fixed locations.
- If the snapshot tool is unavailable or returns an error, do not repeat the same blocked path. Record or report the blocker via `state/current_state.md` or an appropriate report.

{checklist}

## Plan
Based on your observations, decide what to do next.

**Message quality check (MUST)**: Before sending delegation/report/escalation, verify required fields in `common_knowledge/communication/message-quality-protocol.md`

**[MUST] If you identify anything that requires action, you MUST formalize it as a task. "Acknowledged but no action taken" is prohibited.**
Use one of the following to create a concrete action:
- Delegate to subordinates → `delegate_task`
- Do it yourself → record the next action in `state/current_state.md`; do not start hands-on work during normal Heartbeat
- Immediate follow-up → `send_message` / `call_human`

### Checklist
- Background task results: Check task_results / background_notifications in `heartbeat_observe_snapshot` for completed tasks and follow up as needed
- **MUST**: If recent chat/inbox messages contain unhandled instructions from humans or Animas, concretize them via direct handling, `delegate_task`, `send_message`, `call_human`, or `state/current_state.md`
- STALE / near-deadline tasks: Follow up with assignee (send_message), escalate to supervisor if needed
- Long-stalled waiting tasks (24h+): Send status check or reminder
- If there is a blocker: report only (send_message / call_human)
- Only if ALL checks have no actionable items: HEARTBEAT_OK

**Important: Do not perform actual work (code changes, file edits, research, etc.) in this phase.**
**Task execution is handled automatically in a separate session.**

**Delegation guidelines**: When using `delegate_task`, follow the writing principles and forbidden patterns in `read_memory_file(path="common_knowledge/operations/task-delegation-guide.md")` (MUST). Do not use `submit_tasks` during normal Heartbeat.

## Reflect
After completing the above observation and planning, state any insights or observations in the following format if you have them.
You may omit this if you have nothing to add.

[REFLECTION]
(Describe insights, observations, or pattern recognition here)
[/REFLECTION]
