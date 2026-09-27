---
name: google-tasks-tool
description: >-
  Google Tasks integration tool. It uses OAuth2 to list, add, and update task lists and tasks.
  Use when: Use when: you need to fetch the TODO list, add tasks, update completion, or switch task lists.
tags: [tasks, google, todo, external]
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and translate only exposed values in the frontmatter. Please provide the content to translate.# Google Tasks Tool

An external tool for operating task lists and tasks via the Google Tasks API.## How to Call

**Bash**: Run with `animaworks-tool google_tasks <サブコマンド> [引数]`## Action List### list_tasklists — Task List Overview
```bash
animaworks-tool google_tasks tasklists [-n 50]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| max_results | integer | 50 | Maximum number of results to retrieve |### list_tasks — Task List
```bash
animaworks-tool google_tasks list <タスクリストID> [-n 50] [--no-completed]
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tasklist_id | string | Yes | Task list ID |
| max_results | integer | 50 | Maximum number of results to retrieve |
| show_completed | boolean | true | Whether to include completed tasks |

Use when:### insert_task — Add Task
```bash
animaworks-tool google_tasks add <タスクリストID> "タスク名" [--notes メモ] [--due 日時]
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tasklist_id | string | Yes | Task list ID |
| title | string | Yes | Task name |
| notes | string | No | Notes |
| due | string | No | Deadline (RFC 3339) |### insert_tasklist — Create Task List
```bash
animaworks-tool google_tasks new-list "リスト名"
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| title | string | Yes | List name |### update_task — Task Update
Updates the title, notes, deadline, and completion status of a specified task (only the specified items are updated).

```bash
animaworks-tool google_tasks update <タスクリストID> <タスクID> [--title タイトル] [--notes メモ] [--due 日時] [--status completed|needsAction]
```

| Parameter | Type | Required | Description |
|-----------|-----|----------|-------------|
| tasklist_id | string | Yes | Task list ID |
| task_id | string | Yes | Task ID |
| title | string | No | New title |
| notes | string | No | Notes |
| due | string | No | Deadline (RFC 3339) |
| status | string | No | `needsAction` (incomplete) or `completed` (complete). Specify at least one of title/notes/due/status. |### update_tasklist — Update Task List Name
```bash
animaworks-tool google_tasks update-list <タスクリストID> "新しいリスト名"
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tasklist_id | string | Yes | Task list ID |
| title | string | Yes | New list name |## Notes

- OAuth2 authentication flow is required on first use
- Place credentials.json in `~/.animaworks/credentials/google_tasks/` (the same OAuth client as Gmail/Calendar can be copied)