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

## What Does Not Belong On TaskBoard

TaskBoard is for items where someone must work or make a decision next. Heartbeat or monitoring snapshots MUST NOT be surfaced as work cards.

- Observation results such as Inbox unread 0, state/pending 0, background_notifications 0, or no emergency notification belong in Heartbeat/monitoring logs or an Evidence Ledger.
- `evidence-only monitoring` and "no explicit restart instruction, so no reminder/requeue" are not resumed work, so they must not become blocked/overdue/stale TaskBoard cards.
- If a monitoring snapshot must remain in the task queue for traceability, treat it as archived/suppressed on TaskBoard.
- If `submit_tasks` must enqueue a non-work observation record, set `taskboard_kind: "monitoring_snapshot"`.

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
