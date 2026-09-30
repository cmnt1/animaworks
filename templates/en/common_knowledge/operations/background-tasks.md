# Background Task Execution Guide

## Overview

Some external tools (image generation, 3D model generation, local LLM inference, audio transcription, etc.) can take anywhere from a few minutes to tens of minutes to complete. If you run these directly, the lock will be held for the entire duration, and message reception and heartbeat will stop.

By using `animaworks-tool submit`, you can run tasks in the background and immediately move on to the next task yourself.

At runtime, the **BackgroundTaskManager** in `core/tasks/background.py` handles tool execution and state persistence to `state/background_tasks/{task_id}.json`, while the **PendingTaskExecutor** (`core/tasks/pending_executor.py`) inside the Anima child process monitors the waiting queue written by `animaworks-tool submit` and moves items to `BackgroundTaskManager`.

## When to use submit

### Tools that should always use submit

Subcommands marked with ⚠ in the tool guide (system prompt):

- `image_gen pipeline` / `fullbody` / `bustup` / `icon` / `chibi` / `3d` / `rigging` / `animations`
- `local_llm generate` / `chat`
- `transcribe audio` (subcommand name is `audio`)

Tools whose `EXECUTION_PROFILE` is `background_eligible: true` are registered as background execution candidates via profiles (e.g., `chatwork sync` / `download`). Operational policy should still prioritize the **⚠ mark**.

### Tools that do not require submit

Tools with short execution times (typically under a few tens of seconds):

- `web_search`, `x_search`
- `slack`, `chatwork`, `gmail` (normal operations)
- `github`, `aws_collector`

### Decision criteria

- With ⚠ mark → always use submit
- Without ⚠ mark → execute directly (at `animaworks-tool submit` runtime, a warning may appear on stderr if the profile indicates "short duration")

## Usage

### Basic syntax

```bash
animaworks-tool submit <ツール名> <サブコマンド> [引数...]
```

### Execution example

```bash
# 3Dモデル生成（Meshy API 等）
animaworks-tool submit image_gen 3d assets/avatar_chibi.png

# キャラクター画像一括生成（全ステップ）
animaworks-tool submit image_gen pipeline "1girl, black hair, ..." --negative "lowres, ..." --anima-dir $ANIMAWORKS_ANIMA_DIR

# ローカルLLM推論（Ollama）
animaworks-tool submit local_llm generate "要約してください: ..."

# 音声文字起こし（Whisper 等）— サブコマンドは audio
animaworks-tool submit transcribe audio "/path/to/audio.wav" --language ja
```

### Return value

submit immediately outputs JSON to stdout and exits (`task_id` is a 12-digit hex):

```json
{
  "task_id": "a1b2c3d4e5f6",
  "status": "submitted",
  "tool": "image_gen",
  "subcommand": "3d",
  "message": "バックグラウンドタスクを投入しました。完了時にinboxに通知されます。(task_id: a1b2c3d4e5f6)"
}
```

## Receiving results

1. After submit, the **PendingTaskExecutor** picks up the descriptor from `state/background_tasks/pending/` and executes it in the background via `BackgroundTaskManager.submit` (outside Anima's conversation lock).
2. From execution through completion, the status of the same `task_id` is also saved to **`state/background_tasks/{task_id}.json`**. When `BackgroundTaskManager.submit` / `submit_async` write it out, it is saved to disk **from the first time as `running`** (immediately after assigning a 12-digit UUID `task_id`). On completion it becomes `completed`, and on exception `failed`. The `pending` enum value also exists in the data type, but it is not used in the manager's normal submission flow. **Queue waiting** is a separate concept, represented by the descriptor in `state/background_tasks/pending/*.json`.
3. On completion, `_on_background_task_complete` writes a Markdown notification to **`state/background_notifications/{task_id}.md`**.
4. At the next **heartbeat**, `drain_background_notifications()` reads and deletes the relevant `.md`, and it is injected into the context.
5. If WebSocket in the Web UI or human notifications of the `call_human` family are enabled, they may also be delivered at the same completion timing.

The tool **`list_background_tasks`** provides a merged list of memory and disk, and **`check_background_task`** allows you to reference the status of a specified `task_id` (both correspond to `list_tasks` / `get_task` in `BackgroundTaskManager`).

## Handling failures

- If the notification says "failure":
  1. Check the error details
  2. Identify the cause (API key not set, timeout, argument error, etc.)
  3. Fix the issue and submit again
  4. If it cannot be resolved, report to the supervisor

- If JSON remains in `processing/` due to a **crash or abnormal termination**, the **PendingTaskExecutor** will recover it at Anima process startup:
  - **Command type** (`animaworks-tool submit`): `state/background_tasks/pending/processing/*.json` → `state/background_tasks/pending/failed/`
  - **LLM type** is managed with regular tasks and attempt IDs, and descriptors are not recovered. Incomplete work leaves a pending status and a persistent needs-review notification. Check the actual side effects before explicitly resuming.
  Old LLM files are only evidence of migration. Do not move or regenerate them for resumption.

## Common mistakes

### Executing directly

```bash
# 悪い例: 直接実行 → 長時間ロックされうる
animaworks-tool image_gen 3d assets/avatar_chibi.png -j

# 良い例: submit で非同期実行
animaworks-tool submit image_gen 3d assets/avatar_chibi.png
```

If you execute directly, you have no choice but to wait until the task completes. Always use submit from next time onward.

### Omitting the transcribe subcommand

```bash
# 悪い例: audio サブコマンドがないと意図したプロファイル判定にならない
animaworks-tool submit transcribe "/path/to/audio.wav"

# 良い例
animaworks-tool submit transcribe audio "/path/to/audio.wav"
```

### Waiting for results after submit

Once you submit, move on to the next task immediately. Results are incorporated via the notification file for heartbeat, so polling or waiting is unnecessary.

## Technical details (reference)

### BackgroundTaskManager（`core/tasks/background.py`）

- **Role**: Runs long-running tool calls as background `asyncio` tasks and, on completion or failure, `on_complete` (an optional asynchronous callback) `await`. The constructor `state/background_tasks/` `mkdir(parents=True)`.
- **Synchronous tools**: `submit(tool_name, tool_args, execute_fn)` → execute `execute_fn(name, args) -> str | None` in a thread pool using `run_in_executor(None, ...)`.
- **Asynchronous tools**: `submit_async` (with the same signature, `execute_fn` is `Awaitable[str]`) → `await execute_fn(...)` on the event loop.
- **Scheduling**: Wrapped in `asyncio.create_task(..., name=f"bg-{task_id}")`. On completion, remove the corresponding entry from `_async_tasks`.
- **Persistence**: After each change, `_save_task` `to_dict()` to `state/background_tasks/{task_id}.json` (`ensure_ascii=False`, `indent=2`). If the JSON is corrupted, log a warning with `_load_task` and then `None`.
- **Queries**: `get_task` prioritizes in-memory data, falling back to disk. `list_tasks(status=...)` merges with `*.json` on disk and sorts by `created_at` in descending order. `active_count` is the number of in-memory `RUNNING`.
- **`on_complete`**: Even if an exception occurs inside a callback, the task’s completion/failure status is preserved; the failure is only recorded in the log.
- **Qualified tool names** (`is_eligible`) merge the following **3 layers** (later layers take precedence). Keys are used as-is for dictionary lookup (both Mode A schema names `generate_3d_model` and Mode S submission names `image_gen:3d` may be present):
  1. Code defaults `_DEFAULT_ELIGIBLE_TOOLS` (values are approximate durations in seconds; current keys):
     `generate_character_assets`, `generate_fullbody`, `generate_bustup`, `generate_icon`, `generate_chibi`, `generate_3d_model`, `generate_rigged_model`, `generate_animations` (30 each), `local_llm` / `run_command` (60 each)
  2. Via `BackgroundTaskManager.from_profiles`, extract subcommands from `EXECUTION_PROFILE` in each module using `background_eligible: true` (`core.integrations._base.get_eligible_tools_from_profiles`). Keys are `"{tool_name}:{subcmd}"`, and durations are `expected_seconds` (60 if unset)
  3. `background_task.eligible_tools` in `config.json` — override each key’s duration with `threshold_s`
- **Disabling**: Setting `background_task.enabled: false` to `config.json` means `BackgroundTaskManager` itself is not created (in that case, the submit queue is still picked up, but the executor will issue a warning).
- **Cleanup**: `cleanup_old_tasks(max_age_hours=24)` deletes (1) JSON files whose `completed_at` exceeds the specified time in `completed` / `failed`, and (2) files where `running` and `created_at` is more than **48 hours** in the past (orphans left by process crashes, etc.). The return value is the number of deleted files. The caller specifies the retention period using `max_age_hours`; there is no corresponding `config.json` configuration key.

### Other APIs in the same file: `rotate_dm_logs`

`core/tasks/background.py` also contains `rotate_dm_logs(shared_dir, max_age_days=7)`, which is **independent of background tool execution**. Among `shared/dm_logs/*.jsonl`, lines whose entry `ts` is older than the threshold are appended to `{stem}.{YYYYMMDD}.archive.jsonl` as an archive and removed from the active file. The actual processing is done by `_rotate_dm_logs_sync` (offloaded via `run_in_executor`).

### Command-type tasks (`animaworks-tool submit`)

1. `animaworks-tool submit` writes a descriptor to `state/background_tasks/pending/{task_id}.json` (`ANIMAWORKS_ANIMA_DIR` required).
2. The PendingTaskExecutor's watcher monitors `pending/` at intervals of up to **3 seconds** (immediate execution also possible via `wake()`).
3. `pending/*.json` → renames to `pending/processing/`, then `execute_pending_task`.
4. Command type internally launches `animaworks-tool … -j` as a **subprocess**. **Wall-clock timeout per execution is 1800 seconds (30 minutes)** (`pending_executor._PENDING_TASK_SUBPROCESS_TIMEOUT`). On success, the file in processing is deleted. On exception, it moves to `pending/failed/`.
5. The actual processing is delegated to `BackgroundTaskManager.submit(composite_name, tool_args, execute_fn)`. `composite_name` is `tool:subcommand` (e.g., `image_gen:3d`). This is matched against `is_eligible`.
6. On completion, `_on_background_task_complete` writes `state/background_notifications/{task_id}.md`, and `drain_background_notifications()` reads it at heartbeat.

### LLM-type tasks (regular task store)

1. `submit_tasks` / `delegate_task` atomically register the full instruction, context, completion conditions, constraints, model, and dependencies.
2. The watcher retrieves executable tasks and creates attempts in the same transaction. It checks dependencies and configured worker capacity, and limits non-parallel constraints to the same batch.
3. If an attempt ends without `done` / `cancelled` declarations, it returns to pending but is not automatically re-executed. Check side effects and explicitly resume via `submit_tasks(batch_id="resume", tasks=[{"task_id":"ID","resume":true}])` if necessary.
4. Results may be referenceable via `state/task_results/{task_id}.md`, but the regular store is the source of truth for status, input, and attempts. Completion is declared via `update_task` and should not be inferred from LLM responses or file existence.
5. Needs-review and completion notifications are persisted and delivered without depending on periodic heartbeats. Do not reconstruct execution input from DMs.

Do not directly edit SQLite or old task files; use the task tools. This is a separate mechanism from the command-type pipeline described above.

### File lifecycle

**Command type** (waiting queue in `animaworks-tool submit`):

```
state/background_tasks/pending/*.json
  → pending/processing/*.json
  → 成功: 削除 | 失敗: pending/failed/*.json
```

Also, the **task status file** (for the entire execution):

```
state/background_tasks/{task_id}.json   # running → completed / failed
```

**LLM type** (`submit_tasks` / `delegate_task`):

```
保存済み入力 → 実行可能pending → 取得済み試行（in_progress）
  → done/cancelled宣言、またはpending + 永続的な要確認通知
  → 明示resumeで保存済み入力を使う新しい試行
```

The command-type file recovery above does not apply to LLM tasks. Old LLM JSONL and descriptors are migration/export formats and are not signals to start execution.
