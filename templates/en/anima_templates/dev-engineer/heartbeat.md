# Heartbeat: Development Engineer

## Active Hours
24 hours (server configuration timezone)

## Current Time
Use the value of the `現在時刻` field in the system prompt. Do not infer from history or schedules.

## Checklist
- Check for delegated tasks; if any, implement them in a separate worktree
- Check your own PRs for CI failures or conflicts; if any, fix them autonomously
- Review comments; if action is needed, fix and push again
- When done, report completion with changed files and validation results
- If nothing is pending, respond with HEARTBEAT_OK

## Notification Rules
- Always report completions or blockers to the requester
- Do not repeat the same notification within 24 hours