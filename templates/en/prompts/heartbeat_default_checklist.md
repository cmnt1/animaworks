- Use `status: ok`'s `Current Pre-Observed Heartbeat Snapshot` as confirmation evidence. If not available, call `heartbeat_observe_snapshot`
- Check in-progress tasks in current_state.md and STALE / tasks waiting over 24 hours in list_tasks, and provide evidence
- Check all channels where you are a member (general and your department; ops if you are a member) with read_channel, and state whether there are any mentions of you. Do not post mere praise or approval
- Check whether you can access the necessary external tools and whether there are any blockers in in-progress tasks
- Immediately report blockers such as missing files, insufficient permissions, unmet prerequisites, or unclear instructions to the requester. For serious blockers exceeding 30 minutes, also send call_human
- Include HEARTBEAT_OK only in responses where it has been confirmed that all of the above have been resolved

Board posting decisions follow `common_knowledge/communication/broadcasting-guide.md`.
