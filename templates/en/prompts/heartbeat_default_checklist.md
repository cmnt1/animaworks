- **MUST**: Use a `Current Pre-Observed Heartbeat Snapshot` with `status: ok` for fixed-scope checks and do not call the tool again. If absent, call `heartbeat_observe_snapshot` as the fallback
- **MUST**: Check current_state.md for in-progress tasks and state findings as evidence. Always check before deciding "idle" or "waiting"
- **MUST**: Check task queue for STALE tasks (⚠️ STALE). Cite task_queue in `heartbeat_observe_snapshot` as evidence. Never return HEARTBEAT_OK while STALE tasks exist
- **MUST**: Check for waiting tasks stalled 24+ hours. If stalled, send status check or reminder
- **MUST**: Board check — Run `read_channel(...)` for **every channel you are a member of**. At minimum, `general` and your department channel (`property` / `finance` / `affiliate` / `administration` if applicable). Also `ops` if you are a member. Posts without mentions are picked up here (mentions already land in your inbox). Do **not** post praise/acknowledgment replies. See `common_knowledge/communication/broadcasting-guide.md` for the decision logic
- Whether you can access required external tools (if not, report to supervisor)
- Whether in-progress tasks have blockers
- Whether state/pending/ has unexecuted tasks, citing pending_files in `heartbeat_observe_snapshot`

### Blocker Reporting (MUST)

Report immediately to requester. Do not leave in "waiting" state.

- File/directory not found
- Insufficient permissions / prerequisites not met / technical issues
- Instructions unclear and cannot decide

Report to: Requester (send_message). Critical blockers (30+ min delay): also call_human

### HEARTBEAT_OK Gate (ALL must be true)

- Zero self-assigned pending tasks (or all delegated)
- `read_channel` executed with no mentions targeting you
- Zero STALE / OVERDUE tasks
- No unaddressed self-assigned tasks in current_state.md
- A `status: ok` pre-observed snapshot or direct `heartbeat_observe_snapshot` result is available

If any condition is unmet, describe the action you are taking.
