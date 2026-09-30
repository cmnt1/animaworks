# Background Task Execution Guide

## Overview

Some external tools (image generation, 3D model generation, local LLM inference, audio transcription, etc.) can take anywhere from a few minutes to tens of minutes to complete. If you run these directly, the lock will be held for the entire duration, and message reception and heartbeat will stop.

By using `animaworks-tool submit`, you can run tasks in the background and immediately move on to the next task yourself.

`animaworks-tool submit` registers a TaskStore input with `task_type="command"`. The **PendingTaskExecutor** (`core/tasks/pending_executor.py`) in the Anima child process claims an attempt, and the **BackgroundTaskManager** (`core/tasks/background.py`) runs the tool in the background. TaskStore records the attempt; the compatibility result JSON remains at `state/background_tasks/{task_id}.json`.

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

1. Submit atomically registers a `task_type="command"` input in TaskStore. PendingTaskExecutor claims its attempt and asks BackgroundTaskManager to run it outside Anima's conversation lock.
2. TaskStore records the attempt and its result reference. For compatibility with existing query tools, `state/background_tasks/{task_id}.json` uses the same task ID and records `running` → `completed` / `failed`.
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

- After a crash, TaskStore checks the attempt owner's liveness. A confirmed-dead attempt is recorded as pending for review; command work is never automatically replayed because side effects may already have happened. Do not treat a result JSON still marked `running` as completion. Verify actual side effects before explicitly resuming.

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
- **Synchronous tools**: `submit(tool_name, tool_args, execute_fn, task_id=None)` → execute `execute_fn(name, args) -> str | None` in a thread pool using `run_in_executor(None, ...)`. The manager generates an ID when omitted; CLI command tasks pass the TaskStore ID.
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
- **Disabling**: Setting `background_task.enabled: false` means `BackgroundTaskManager` is not created. Submit still registers the TaskStore task, but the attempt returns to pending with a needs-review notification.
- **Cleanup**: `cleanup_old_tasks(max_age_hours=24)` deletes (1) JSON files whose `completed_at` exceeds the specified time in `completed` / `failed`, and (2) files where `running` and `created_at` is more than **48 hours** in the past (orphans left by process crashes, etc.). The return value is the number of deleted files. The caller specifies the retention period using `max_age_hours`; there is no corresponding `config.json` configuration key.

### Other APIs in the same file: `rotate_dm_logs`

`core/tasks/background.py` also contains `rotate_dm_logs(shared_dir, max_age_days=7)`, which is **independent of background tool execution**. Among `shared/dm_logs/*.jsonl`, lines whose entry `ts` is older than the threshold are appended to `{stem}.{YYYYMMDD}.archive.jsonl` as an archive and removed from the active file. The actual processing is done by `_rotate_dm_logs_sync` (offloaded via `run_in_executor`).

### Command-type tasks (`animaworks-tool submit`)

1. `animaworks-tool submit` atomically registers a TaskStore input containing `task_type="command"`, tool name, arguments, anima, and task ID (`ANIMAWORKS_ANIMA_DIR` is required).
2. The TaskStore watcher uses the existing claim / attempt mechanism. BackgroundTaskManager uses the same task ID for its compatibility result file.
3. Command type launches `animaworks-tool … -j` as a **subprocess**. **Wall-clock timeout per execution is 1800 seconds (30 minutes)** (`pending_executor._PENDING_TASK_SUBPROCESS_TIMEOUT`).
4. Stdout or the error is saved to `state/task_results/{task_id}/{attempt_token}.md` and referenced by the TaskStore attempt. TaskStore is authoritative for inputs, status, and attempts.
5. BackgroundTaskManager records `running` → `completed` / `failed` in `state/background_tasks/{task_id}.json`. `_on_background_task_complete` writes `state/background_notifications/{task_id}.md`, which heartbeat drains.

### Migrating legacy command descriptors

Existing `state/background_tasks/pending/*.json` files are not watched by the new runtime. While the anima is stopped, run `animaworks task-store migrate --anima NAME --backup PATH` to validate and import unprocessed top-level descriptors into TaskStore. Source files are retained as evidence. Descriptors in `processing/` or `failed/` are not replayed or imported automatically; they are left with a warning for operator review of possible side effects.

### LLM-type tasks (regular task store)

1. `submit_tasks` / `delegate_task` atomically register the full instruction, context, completion conditions, constraints, model, and dependencies.
2. The watcher retrieves executable tasks and creates attempts in the same transaction. It checks dependencies and configured worker capacity, and limits non-parallel constraints to the same batch.
3. If an attempt ends without `done` / `cancelled` declarations, it returns to pending but is not automatically re-executed. Check side effects and explicitly resume via `submit_tasks(batch_id="resume", tasks=[{"task_id":"ID","resume":true}])` if necessary.
4. Results may be referenceable via `state/task_results/{task_id}.md`, but the regular store is the source of truth for status, input, and attempts. Completion is declared via `update_task` and should not be inferred from LLM responses or file existence.
5. Needs-review and completion notifications are persisted and delivered without depending on periodic heartbeats. Do not reconstruct execution input from DMs.

Do not directly edit SQLite or old task files; use the task tools. This is a separate mechanism from the command-type pipeline described above.

### File lifecycle

**Command type** (`animaworks-tool submit`):

```
TaskStore command input → claimed attempt
  → success: done | failure/interruption: pending for review (no automatic retry)
state/task_results/{task_id}/{attempt_token}.md  # attempt output / error
state/background_tasks/{task_id}.json           # compatibility result: running → completed / failed
```

**LLM type** (`submit_tasks` / `delegate_task`):

```
保存済み入力 → 実行可能pending → 取得済み試行（in_progress）
  → done/cancelled宣言、またはpending + 永続的な要確認通知
  → 明示resumeで保存済み入力を使う新しい試行
```

Command and LLM work use different input payloads, but both are claimed and tracked through TaskStore attempts. Legacy LLM JSONL and `state/pending/` descriptors are migration/export formats, not signals to start execution.
