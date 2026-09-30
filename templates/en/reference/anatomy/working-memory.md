# Working Memory (state/） Technical Reference

Detailed specification of the `state/` directory that manages Anima's working status.
Includes prompt injection logic, size control, migration, and lock control.

---

## state/ Directory Structure

```
state/
├── current_state.md          # ワーキングメモリ（自由形式Markdown）
├── task_results/              # TaskExec完了結果
│   └── {task_id}/{attempt_token}.md
├── conversation.json          # 会話状態
├── conversations/             # スレッド別会話ファイル
├── recovery_note.md           # クラッシュ復旧ノート
├── heartbeat_checkpoint.json  # Heartbeatチェックポイント
└── pending_procedures.json    # 保留中の手続き追跡
```

---

## current_state.md

### Role

Anima's working memory. Records in free-form what is currently being done, what has been observed, and what blockers exist. Not for task management, but for situational awareness.

Task tracking is handled by the host-managed authoritative TaskStore. For confirmation, use `list_tasks`; for changes, use the task tools. Do not directly edit the DB or queue files.

### Size Control

| Parameter | Value | Source |
|-----------|-----|-------|
| Display limit | 3000 characters | `_CURRENT_STATE_MAX_CHARS` (builder.py) |
| Disk trim limit | 8000 characters (default) | `heartbeat.current_state_max_chars` (0 = disabled) |
| Inbox limit | 500 characters | `min(_state_max, 500)` within builder.py |

**Session boundaries**:

- Normal Heartbeat / cron / conversation finalization preserves `current_state.md`
- Even if the current status is included in the session summary, it is only written when `current_state.md` is empty/idle
- Old state with no active tasks may be archived by TaskBoard housekeeping. Active tasks protect the state even when not visible

**Optional cleanup during Heartbeat**:

1. If `heartbeat.current_state_max_chars` is greater than 0 and `current_state.md` exceeds that value before Heartbeat starts, an instruction to "organize and compress" is injected into the Heartbeat prompt
2. After Heartbeat or cron completes, `_enforce_state_size_limit()` is executed
3. The amount exceeding the configured limit is moved to the current day's episode memory (`episodes/{date}.md`) as `## current_state.md overflow archived`
4. The configured number of trailing characters is preserved, adjusted at line breaks (if a line break exists within the first 20%, truncate there)

### Prompt Injection

| Trigger | Behavior |
|---------|------|
| `chat` | Full injection (3000-character limit, scale applied) |
| `inbox` | Limited to 500 characters maximum |
| `heartbeat` / `cron` | Full injection (3000-character limit) |
| `task` | **Not injected** (Minimal tier) |

When injecting, if only `status: idle` is present, the section itself is omitted.
Otherwise, it is injected with an emphasis header using the `builder/task_in_progress` template.

### Lock Control

The `_state_file_lock` (`asyncio.Lock`) of `core/anima/digital_anima.py` prevents concurrent writes to `current_state.md`.

`_is_state_file(path)` returns `True` only to `state/current_state.md`. For writes via `write_memory_file`, a lock is automatically acquired on this file.

### Path Resolution (Backward Compatibility)

If `state/current_task.md` is specified in `read_memory_file` / `write_memory_file`, it is automatically resolved to `state/current_state.md` (`handler_memory.py`).

---

## pending.md (Deprecated)

`state/pending.md` is merged into `current_state.md` and then automatically deleted.

### Migration (at MemoryManager initialization)

1. If `state/current_task.md` exists and `state/current_state.md` does not exist → rename
2. If both exist → prefer `current_state.md`, log a warning
3. If `state/pending.md` exists with content → append to `current_state.md` as `## Migrated from pending.md`, then delete
4. If `state/pending.md` is empty → delete

---

## Old Task Files

`state/task_queue.jsonl` and `state/pending/` are retained only as evidence for migration and export. They are not active queues. The operator stops legacy write processes, explicitly imports with a backup, and then starts the authoritative runtime. Do not delete, re-inject, or fabricate files to resume.

## Task Execution and Results

The host stores the original instruction and tasks in bulk, retrieves executable work, and records each attempt. `in_progress` is host-managed. The agent declares `done` / `pending` / `cancelled` via `update_task`. Dependencies and reasons for action are confirmed via `list_tasks(detail=true)`. Pending does not mean retry. After resolving the cause, explicitly resume the same task via `submit_tasks(..., tasks=[{"task_id": "ID", "resume": true}])`.

Accepted result summaries are saved to `state/task_results/{task_id}/{attempt_token}.md` (up to 2000 characters). Subsequent steps receive the accepted result chosen by the host. Do not judge completion based solely on the existence of old files. Preserve the original record, write the result, and do not pretend an attempt succeeded.

Long-running command tools are also registered in TaskStore as `task_type="command"`. PendingTaskExecutor claims an attempt and BackgroundTaskManager runs it. The attempt is recorded in TaskStore, while `state/background_tasks/{task_id}.json` and the completion notification remain available for compatibility. See `operations/background-tasks.md` and `operations/task-management.md` for details.

## read_subordinate_state

When a supervisor calls `read_subordinate_state(name="部下名")`, only the subordinate's `state/current_state.md` is read (`pending.md` is excluded).
