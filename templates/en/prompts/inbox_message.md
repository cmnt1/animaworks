You have messages in your inbox. Review the following and reply appropriately.

{messages}

## Response Guidelines
- Answer questions directly
- Reply with acknowledgment and timeline for requests
- **[MUST] If you identify work that needs to be done, make it durable. Do not just reply and forget. Inbox is a short-lived session — multi-step work you start here is lost when the session ends.**
  - Delegate to subordinates → `delegate_task` (if you have any)
  - Light work that finishes in 1–2 steps → fine to execute inline in this session
  - Multi-step / long-running work you do yourself → **do NOT attempt it inline** (it will be lost). Use `write_memory_file` to append the work and next action to `state/pending.md` (backlog) and reflect it in `state/current_state.md`. The next heartbeat will plan and execute it. In your reply, state the plan (key points and rough steps)
- Keep replies concise (no lengthy responses)

### Replying to External Platform Messages
When a message has `[reply_instruction: ...]` metadata:
- **Always follow the instruction** to reply
- If the instruction is in `use tool ...` form, call that tool directly
- If the instruction is a shell command, execute it via `Bash`
- Replace `{reply_content}` with your actual reply text
- Do NOT use `send_message` (it sends DMs, not thread replies)

When a message has `[auto_reply: ...]` metadata:
- Your entire output will be auto-posted to the external platform
- Do not write startup/progress narration such as "I'll check first" or "I'll summarize this as the final response"
- After using tools, write only the final reply that should be posted
- Do not repeat the same meaning. If you repeated yourself, keep only one final version

**Delegation guidelines**: When using `delegate_task`, follow the writing principles and forbidden patterns in `read_memory_file(path="common_knowledge/operations/task-delegation-guide.md")` (MUST). Do not use `submit_tasks` during normal Inbox processing.
