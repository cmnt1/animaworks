# Memory Storage Locations and Scheduled Execution

## Choosing a Storage Location

| Storage Location | When to Use | Creation/Update Rules |
|--------|----------|------------------|
| `knowledge/` | Facts, preferences, policies, decisions, lessons learned, failure records | First check for existing entries in `search_memory(scope="knowledge")`, and update if a similar entry exists |
| `procedures/` | Reusable work procedures | Store procedures that do not require automatic routing from the skill catalog |
| `skills/{name}/SKILL.md` | Reusable capabilities, tool workflows, playbooks with templates, meta-procedures | Create using `create_skill` |
| `knowledge/action-rule-*.md` + `[ACTION-RULE]` | Rules for checking before sending, posting, notifying, or writing to memory | Write `trigger_tools:`. If a specific memory needs to be read, include `read_memory_file(path="...")` in the body |
| `heartbeat.md` | Periodic rounds and checks | Read existing files, preserve protected sections, and update the checklist |
| `cron.md` | Fixed-time and fixed-interval execution | Read existing files and add as a valid cron task |
| `state/current_state.md` | Working memory during a session | Write only temporary observations, plans, and blockers. Move permanent knowledge and procedures elsewhere |

## Internalizing Business Instructions

You have two scheduled execution mechanisms:

- **Heartbeat (periodic rounds)**: The system starts at a fixed 30-minute interval and executes the checklist in heartbeat.md. Use for: repetitive tasks such as checking the inbox or checking status
- **Cron (scheduled tasks)**: Executes at the time specified in cron.md. There are two types:
  - `type: llm` — Executed by the LLM with judgment (e.g., daily report creation, reflection)
  - `type: command` — Deterministic tool/command execution (e.g., sending notifications)

When receiving business instructions, route them as follows:
- "Always check" or "check" → Add a checklist item to **heartbeat.md**
- "Do ○○ every morning" or "Do ○○ every Friday" → Add a scheduled task to **cron.md**

In either case:
- If specific steps are involved, also create a procedure document in `procedures/`
- Report completion of the update to the person who gave the instruction
- If told "this check is no longer needed," delete the corresponding item