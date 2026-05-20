You have messages in your inbox. Review the following and reply appropriately.

{messages}

## Response Guidelines
- Answer questions directly
- Reply with acknowledgment and timeline for requests
- **[MUST] If you identify work that needs to be done, you MUST formalize it as a task. Do not just reply and forget.**
  - Delegate to subordinates → `delegate_task`
  - Do it yourself → execute directly in this session, and if follow-up tracking is needed, record it in `state/current_state.md` or an explicit background execution workflow
- Keep replies concise (no lengthy responses)

### Replying to External Platform Messages
When a message has `[reply_instruction: ...]` metadata:
- **Always follow the instruction** to reply
- If the instruction is in `use tool ...` form, call that tool directly
- If the instruction is a shell command, execute it via `Bash`
- Replace `{reply_content}` with your actual reply text
- Do NOT use `send_message` (it sends DMs, not thread replies)

**Delegation guidelines**: When using `delegate_task`, follow the writing principles and forbidden patterns in `read_memory_file(path="common_knowledge/operations/task-delegation-guide.md")` (MUST). Do not use `submit_tasks` during normal Inbox processing.
