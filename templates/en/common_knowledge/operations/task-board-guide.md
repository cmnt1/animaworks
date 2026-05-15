# Task Board (Human Dashboard)

A shared file for the organization's owner (human) to get a bird's-eye view of all tasks.

## Purpose

AnimaWorks task management is self-contained for agents via `task_queue.jsonl` +
`current_state.md` + `delegate_task`. However, **humans lack a single place to see
everything at a glance**. `shared/task-board.md` solves this as a human-facing dashboard.

## Positioning

| Resource | Purpose | Audience |
|----------|---------|----------|
| `state/task_queue.jsonl` | Task tracking (append-only) | Agents |
| `state/current_state.md` | Current work notes | Individual agent |
| `state/task_results/` | Task execution results | System auto |
| **`shared/task-board.md`** | **All-task overview** | **Human (owner)** |

## Human-Facing Copy Rules

Any `summary`, `title`, or task name shown on the Task Board MUST make sense to a human when the card is read in isolation.

- Start with the work item and its current state. Do not start with internal logs, delegation chains, or pasted raw instructions.
- Briefly include who owns it, what is blocked or waiting, and the next action when relevant.
- Keep message IDs, internal task IDs, long file paths, log excerpts, heartbeat details, and mojibake/raw text out of the card surface. Put those in `instruction`, `description`, or `context` when needed.
- Treat `delegate_task(summary=...)` and `submit_tasks(tasks[].title=...)` as the Task Board card surface; write them as short human-readable labels.
- Bad: `2026-05-15 09:00 JST task confirmed. Following prior non-miyu delegation failure prevention policy...`
- Good: `Morning planning script is waiting on delegation. kanna will ask miyu after checking her current state`

## Format

```markdown
# Task Board

Last updated: YYYY-MM-DD HH:MM by {updater}

## 🔴 Blocked (waiting on human)
| # | Task | Owner | Blocker | Due |
|---|------|-------|---------|-----|

## 🟡 In Progress
| # | Task | Owner | Status | Due |
|---|------|-------|--------|-----|

## 📋 To Do (upcoming)
| # | Task | Owner | Notes | Due |
|---|------|-------|-------|-----|

## ✅ Completed This Week
| Task | Owner | Completed |
|------|-------|-----------|
```

## Operating Rules

1. **The supervisor (CEO-equivalent Anima) manages it**
   - On delegation: update task-board.md before send_message
   - On completion report: move from In Progress → Completed
   - On heartbeat: check overdue tasks, update blocker status

2. **Each agent updates when their task completes**
   - Move from In Progress → ✅ Completed This Week

3. **Weekly reset**
   - Clear previous week from "Completed This Week"
   - Review priorities and deadlines of To Do items

## Slack Sync (Optional)

Use `slack_channel_post` and `slack_channel_update` tools to sync with a pinned
Slack message. `slack_channel_update` (chat.update API) overwrites the message
silently (no notification), making it work as a live dashboard.

> These are gated actions. Usage requires
> `slack_channel_post: yes` / `slack_channel_update: yes` in permissions.json.

### Setup

1. `slack_channel_post` to create initial message → save returned `ts`
2. Pin the message in Slack
3. Use `slack_channel_update` to overwrite on changes

### Storing the ts

Save in `shared/task-board-slack.json`:
```json
{"channel_id": "C0XXXXXXXX", "ts": "1741XXXXXXX.XXXXXX"}
```
