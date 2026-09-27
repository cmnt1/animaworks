---
name: cron-management
description: >-
  cron.mdを正しいフォーマットで読み書きするスキル。定時タスクの追加・更新・削除手順を提供する。
  Use when: cron.mdの編集、cron式の追加、LLM型・コマンド型タスクの追加・削除、定時ジョブのメンテナンスが必要なとき。
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and translate only exposed values. Please provide the content to translate.## Framework-side implementation (for reference)### cron (Scheduled Tasks)

cron **parsing** is handled by `core/supervisor/schedule_parser.py` (`parse_cron_md` / `parse_schedule`), while **registration, execution, and reloading** are managed by `core/supervisor/scheduler_manager.py` (APScheduler, `AsyncIOScheduler(timezone=get_app_timezone())`).### `core/tasks/background.py` (Separate from cron)

This module does **not perform cron scheduling**. It handles background execution of long-running tool calls and DM log rotation. Do not confuse it with cron.

**`BackgroundTaskManager`**

- **Role**: Asynchronously executes target tools on `asyncio` and saves status to disk.
- **Persistence destination**: `state/background_tasks/{task_id}.json` (`pending` / `running` / `completed` / `failed`, result string, error, timestamp).
- **Public API (overview)**:
  - `submit(tool_name, tool_args, execute_fn)` — Runs synchronous execution functions in a thread pool.
  - `submit_async(...)` — Asynchronous `execute_fn` version.
  - `get_task` / `list_tasks` / `active_count` — Queries.
  - `cleanup_old_tasks(max_age_hours=24)` — Deletes completion and failure tasks older than **24 hours**. Additionally, deletes JSON files that have remained in `running` status for over **48 hours** (crash orphans).
- **`from_profiles(anima_dir, ..., profiles, config_eligible)`**: The background target tool set is a **3-layer merge** (later wins).
  1. In-code default `_DEFAULT_ELIGIBLE_TOOLS` (fixed list compatible with Mode A)
  2. Entries from `EXECUTION_PROFILE` to `background_eligible: true` in each tool module (`core.integrations._base.get_eligible_tools_from_profiles`). Keys use `"{tool}:{subcommand}"` format (consistent with Mode S's `submit`)
  3. `config_eligible` passed from `config.json` etc. (explicit override)
- **`is_eligible(tool_name)`**: Can be matched by either of the following names — schema name (e.g., `generate_3d_model`), profile key (e.g., `image_gen:3d`).
- **Examples included in `_DEFAULT_ELIGIBLE_TOOLS` by default** (values are approximate seconds): `generate_character_assets` / `generate_fullbody` / `generate_bustup` / `generate_icon` / `generate_chibi` / `generate_3d_model` / `generate_rigged_model` / `generate_animations` (30 each), `local_llm` / `run_command` (60 each).
- **Completion hook**: `Callable[[BackgroundTask], Awaitable[None]]` can be set in `on_complete`. The application side can write Markdown notifications to `state/background_notifications/` from here (`background.py` itself does not touch the notification directory).

**`rotate_dm_logs`**

- Truncates `shared/dm_logs/*.jsonl` entries at `max_age_days` (default **7 days**), appending old lines to `{stem}.{YYYYMMDD}.archive.jsonl` as an archive. This is not a cron task, but it is defined in the same file as background maintenance, so it is listed here for reference.

---

Use when:## Structure of cron.md### Overall Structure

```markdown
# Cron: {自分の名前}

## タスク名1
schedule: 0 9 * * *
type: llm
タスクの説明文...

## タスク名2
schedule: */5 * * * *
type: command
command: /path/to/script.sh
```
### Rules That Must Be Followed

1. **Each task starts with `## タスク名`** (H2 heading. Do not use H3 or H1)
2. **The `schedule:` line is required** (start with the keyword `schedule:`. Do not make it a `###` heading)
3. **Use only standard 5-field cron expressions for schedules** (`09:00` and `毎週金曜 17:00` are not allowed)
4. **The `type:` line is required** (either `llm` or `command`)
5. **Insert a blank line between tasks** (for readability)### What Not to Do

```markdown
❌ ### */5 * * * *           ← H3見出しにcron式を書いてはいけない
❌ ### 09:00                 ← 自然言語の時刻表記は不可
❌ ### 毎週金曜 17:00         ← 日本語のスケジュール表記は不可
❌ cron: 0 9 * * *           ← キー名は "schedule:" であること（"cron:" ではない）
❌ interval: 5m              ← interval形式は不可
❌ schedule: 0 9 * * * *     ← 6フィールドは不可（5フィールドのみ）
```
### Correct Writing Style

```markdown
✅ schedule: 0 9 * * *       ← "schedule:" + 半角スペース + 5フィールドcron式
✅ schedule: */5 * * * *
✅ schedule: 30 21 * * *
✅ schedule: 0 17 * * 5
```

---## 5-field cron expression reference### Field Configuration

```
schedule: 分 時 日 月 曜日
```

| Field | Position | Range | Description |
|-----------|------|------|------|
| Minute | 1 | 0-59 | Which minute to run |
| Hour | 2 | 0-23 | Which hour to run (24-hour format) |
| Day | 3 | 1-31 | Which day to run |
| Month | 4 | 1-12 | Which month to run |
| Weekday | 5 | 0-6 | Which weekday to run (0=Mon, 6=Sun) |

**Note**: Weekday uses **0=Monday, 6=Sunday** (APScheduler specification. This differs from the common cron convention where 0=Sunday)### Special Characters

| Character | Meaning | Example |
|------|------|-----|
| `*` | All values | `* * * * *` = every minute |
| `*/n` | Interval of n | `*/5 * * * *` = every 5 minutes |
| `n-m` | Range | `0 9-17 * * *` = every hour from 9 AM to 5 PM |
| `n,m` | List | `0 9,12,18 * * *` = 9 AM, 12 PM, 6 PM |
| `n-m/s` | Range + interval | `0 9-17/2 * * *` = every 2 hours from 9 AM to 5 PM |### Frequently Used Schedule Examples#### Daily

| What you want to do | cron expression | Explanation |
|-------------|--------|------|
| Every morning at 9:00 | `0 9 * * *` | minute=0, hour=9 |
| Every morning at 9:30 | `30 9 * * *` | minute=30, hour=9 |
| Every day at 12:00 (noon) | `0 12 * * *` | minute=0, hour=12 |
| Every day at 18:00 | `0 18 * * *` | minute=0, hour=18 |
| Every evening at 21:30 | `30 21 * * *` | minute=30, hour=21 |
| Every day at 2:00 AM | `0 2 * * *` | minute=0, hour=2 |#### Interval-based

| What you want to do | cron expression | Explanation |
|-------------|--------|------|
| Every 5 minutes | `*/5 * * * *` | minute=*/5（0,5,10,...,55） |
| Every 10 minutes | `*/10 * * * *` | minute=*/10（0,10,20,...,50） |
| Every 15 minutes | `*/15 * * * *` | minute=*/15（0,15,30,45） |
| Every 30 minutes | `*/30 * * * *` | minute=*/30（0,30） |
| Every hour | `0 * * * *` | At minute 0 of every hour |
| Every 2 hours | `0 */2 * * *` | At minute 0 of hours 0, 2, 4, ..., 22 |
| Every 5 minutes during business hours only | `*/5 9-17 * * *` | Every 5 minutes from 9:00 to 17:55 |
| Every hour during business hours only | `0 9-17 * * *` | At the top of every hour from 9:00 to 17:00 |#### Day-of-Week Patterns

| Desired Action | cron Expression | Explanation |
|-------------|--------|------|
| Every weekday at 9:00 AM | `0 9 * * 0-4` | Day of week = 0-4 (Mon–Fri) |
| Every Monday at 9:00 AM | `0 9 * * 0` | Day of week = 0 (Mon) |
| Every Friday at 5:00 PM | `0 17 * * 4` | Day of week = 4 (Fri) |
| Every Friday at 6:00 PM | `0 18 * * 4` | Day of week = 4 (Fri) |
| Every 30 minutes during weekday business hours | `*/30 9-17 * * 0-4` | Weekdays 9:00 AM–5:30 PM |
| Every weekend at 10:00 AM | `0 10 * * 5,6` | Day of week = 5,6 (Sat, Sun) |#### Monthly

| Desired action | cron expression | Description |
|-------------|--------|------|
| 9:00 on the 1st of every month | `0 9 1 * *` | day=1 |
| 12:00 on the 15th of every month | `0 12 15 * *` | day=15 |
| Near the last business day of every month (28th) | `0 17 28 * *` | day=28 (approximate) |
| 9:00 on the first day of each quarter (Jan, Apr, Jul, Oct) | `0 9 1 1,4,7,10 *` | month=1,4,7,10 |

---## Task Type Details### type: llm — LLM judgment task

Tasks that require thinking and judgment. After `schedule:` and `type: llm`, write the task content in free-form text.

```markdown
## 毎朝の業務計画
schedule: 0 9 * * *
type: llm
長期記憶から昨日の進捗を確認し、今日のタスクを計画する。
理念と目標に照らして優先順位を判断する。
結果は state/current_state.md に書き出す。
```

- The description is passed directly to the LLM as a prompt
- It is effective to clearly specify the concrete output (what to write out)
- Multiple lines are OK
- Consider using a fenced code block in the body (\`\`\`）が含まれると、パーサーが警告ログを出す（確定コマンドなら `type: command`)### type: command — Command execution task

A bash command or tool call executed deterministically.#### Pattern A: bash command

```markdown
## バックアップ実行
schedule: 0 2 * * *
type: command
command: /usr/local/bin/backup.sh
```

- Write the command to execute in `command:` on a single line
- Shell redirection (`>`, `>>`, `|`) is allowed
- Multi-line commands are not recommended (either combine them into one line or use a script file)#### Pattern B: Tool Invocation

```markdown
## Slack朝の通知
schedule: 0 9 * * 0-4
type: command
tool: slack_channel_post
args:
  channel_id: "C0123456789"
  text: "おはようございます！"
```

- `tool:` contains the tool name (a schema name included in the permission configuration of `permissions.json`. For example, Slack posting uses `slack_channel_post`)
- From `args:` onward, use YAML block format with a 2-space indent
- Executed via `ToolHandler.handle(tool, args)`, and the resulting string is treated as the equivalent of stdout### Option: skip_pattern

`type: command` A **follow-up cron LLM** (an analysis session with heartbeat-equivalent context) that runs only when the command **succeeds** (`exit_code == 0`) and standard output is non-empty is **suppressed** when stdout matches this regular expression.

```markdown
## Chatwork未返信チェック
schedule: */5 * * * *
type: command
command: chatwork_cli.py unreplied --json
skip_pattern: "^\[\]$"
```

- Write a regular expression in `skip_pattern:` (at runtime, `re.search(skip_pattern, stdout)`)
- If the regular expression contains YAML special characters such as `[]`, enclose it in quotes (`"..."` or `'...'`). The parser automatically removes the outer quotes
- **At parse time**, an invalid regular expression → a warning log is issued and `skip_pattern` is treated as unset (no follow-up suppression)
- **At runtime**, if `re.search` throws an exception (e.g., a residual invalid pattern) → a warning log is issued and the follow-up runs **without suppression**
- In the example above, the follow-up is skipped when the number of unreplied messages is 0 (`[]`)### Option: trigger_heartbeat

Controls on a per-task basis whether a follow-up cron LLM is run upon command success (following the evaluation order of `SchedulerManager._run_cron_task`).

```markdown
## Chatwork未返信チェック
schedule: */15 * * * *
type: command
command: animaworks-tool chatwork unreplied
skip_pattern: "^\[\]$"
trigger_heartbeat: false
```

- **Conditions for considering a follow-up** (when all are met): `exit_code == 0` and stdout (after `.strip()`) is not empty
- **stdout length**: The `stdout` that `run_cron_command` returns to the scheduler is truncated to the first **1000 characters**. This preview is also what is passed to the follow-up LLM. For the full log, refer to `state/cron_logs/` (JSONL)
- `trigger_heartbeat: false` — Even if the above conditions are met, the follow-up cron LLM is **not executed** (evaluated before `skip_pattern`)
- `trigger_heartbeat: true` (default) — If conditions are met, the follow-up is executed (then `skip_pattern` is evaluated)
- Specifying `false`, `no`, or `0` suppresses it. Otherwise, it is treated as true
- The follow-up cron LLM runs with a heartbeat-equivalent prompt filter (background context)
- When `exit_code != 0` or stdout is empty, the follow-up is **not started at all** (`skip_pattern` / `trigger_heartbeat` are irrelevant)

---## Criteria for Choosing Between Types### When to use type: command
- The command to execute is fully determined
- Parameters are fixed (region, cluster name, profile, etc.)
- Judgment of the result is left to the cron LLM session### When to use type: llm
- When the execution content needs to change depending on the situation
- When research combining multiple tools is required
- When human-like judgment and analysis are needed at the execution stage### Forbidden Patterns
- type: llm includes a code block (confirmed command)
  → That command should be type: command
- Written as "execute exactly as instructed" but type: llm
  → LLM cannot accurately reproduce commands. Use type: command### Anima is not someone who memorizes commands
The `type: command` is the same as a human saving a script.
Anima's value lies in its ability to judge based on results.
Leave deterministic execution to the framework,
and have Anima focus on judgment, analysis, and reporting.## Cron Health Notifications (Automatic)

The scheduler generates `state/background_notifications/cron_health_{タイムスタンプ}.md` when it detects issues. These are expected to be read and acted upon in the context of the next heartbeat or cron execution.

**Layer 1 (Setup / immediately after `reload_schedule`)** — Compare `parse_cron_md` results against the raw text:

- A task is defined but **no valid schedule can be registered** (e.g., all expressions are invalid)
- The raw text contains `schedule:` lines with leading whitespace (including indented lines inside code fences; normally, write **`schedule:` at the start of the line (or trim the entire line so it begins with `schedule:`)**)
- The raw text contains the string `schedule:`, but the parser **returns zero tasks**

**Layer 2 (Every 3 hours)** — If at least one registered user cron job exists but the activity_log shows **0** `cron_executed` entries in the last **3 hours**, issue a warning (the job itself may not be running)

---

## cron.md Operating Procedures

### Target Paths and Editing Subordinates

- Read your own `cron.md` via `read_memory_file(path="cron.md")` and update it via `write_memory_file(path="cron.md", ...)`.
- When a supervisor edits a subordinate Anima's `cron.md` / `heartbeat.md` / `injection.md` / `status.json`, do not use Read / Write / Edit / apply_patch / `Path.write_text` / shell redirection, or other direct file operations.
- Edit subordinate management files by specifying them with the write memory tool as in `../{anima_name}/cron.md` (e.g., `../yuki/cron.md`). This applies to all direct and indirect subordinates (children, grandchildren, etc.). `identity.md` is read-only.

### Adding a New Task

1. Load your own `cron.md`
2. Append a new section at the end of the file
3. **Verify the format before writing** (see the checklist below)
4. Write the file

```markdown
## 新しいタスク名
schedule: <5フィールドcron式>
type: llm|command
<説明またはcommand/tool行>
```

### Modifying an Existing Task

1. Load `cron.md`
2. Locate the relevant section (from `## タスク名` to just before the next `##`)
3. Edit the lines to change (`schedule:`, `type:`, description text, etc.)
4. Write the file

### Deleting a Task

1. Load `cron.md`
2. Delete the entire relevant section (from `## タスク名` to just before the next `##`)
3. Write the file

### Temporarily Disabling a Task

Wrapping it in HTML comments makes the parser skip it:

```markdown
<!--
## 一時停止中のタスク
schedule: 0 9 * * *
type: llm
このタスクは一時的に停止中。
-->
```

---

## Pre-Write Checklist

Before updating cron.md, **always** verify the following:

- [ ] Each task starts with `## タスク名` (not `###` or `#`)
- [ ] A `schedule:` line exists (not a `###` heading or natural language)
- [ ] The schedule is a 5-field cron expression (`分 時 日 月 曜日`)
- [ ] Each field's value is within the valid range (minute: 0-59, hour: 0-23, day: 1-31, month: 1-12, weekday: 0-6)
- [ ] A `type:` line exists (`llm` or `command`)
- [ ] For command type, `command:` or `tool:` exists
- [ ] For tool type, the indentation of `args:` is correct (2 spaces)
- [ ] There is a blank line between tasks
- [ ] `schedule:` is not written inside a code block (this can cause health warnings)

### Validation Method

After writing, you can verify that the file parses correctly with the following command:

```bash
# プロジェクトルートで実行。ANIMAWORKS_ANIMA_DIR 未設定時は ~/.animaworks/animas/default を使用
python -c "
from core.supervisor.schedule_parser import parse_cron_md, parse_schedule
import os
from pathlib import Path

cron_path = Path(os.environ.get('ANIMAWORKS_ANIMA_DIR', '~/.animaworks/animas/default')) / 'cron.md'
content = cron_path.expanduser().read_text()
tasks = parse_cron_md(content)
for t in tasks:
    trigger = parse_schedule(t.schedule)
    status = '✅' if trigger else '❌ パース失敗'
    print(f'{status} {t.name}: schedule=\"{t.schedule}\" type={t.type}')
"
```

If all tasks show ✅, it is normal. If ❌ appears, fix the schedule expression.

---

## Complete Example

```markdown
# Cron: example_anima

## 毎朝の業務計画
schedule: 0 9 * * *
type: llm
長期記憶から昨日の進捗を確認し、今日のタスクを計画する。
理念と目標に照らして優先順位を判断する。
結果は state/current_state.md に書き出す。

## Chatwork未返信チェック
schedule: */5 9-18 * * 0-4
type: command
command: chatwork-cli unreplied --json > $ANIMAWORKS_ANIMA_DIR/state/chatwork_unreplied.json
skip_pattern: "^\[\]$"
trigger_heartbeat: false

## Slack朝の挨拶
schedule: 0 9 * * 0-4
type: command
tool: slack_channel_post
args:
  channel_id: "C0123456789"
  text: "おはようございます！今日もよろしくお願いします。"

## 週次振り返り
schedule: 0 17 * * 4
type: llm
今週のepisodes/を読み返し、パターンを抽出してknowledge/に統合する。
改善点があれば procedures/ に手順を追記する。

## 月次レポート
schedule: 0 10 1 * *
type: llm
先月のepisodes/とknowledge/を分析し、月次サマリーレポートを作成する。
レポートは knowledge/monthly_report_YYYY-MM.md として保存する。
```

---

## Common Mistakes and Fixes

| Mistake | Correct Form | Reason |
|--------|------------|------|
| `### */5 * * * *` | `schedule: */5 * * * *` | H3 headings cannot be used as task separators |
| `### 09:00` | `schedule: 0 9 * * *` | Natural language times cannot be parsed |
| `### 毎週金曜 17:00` | `schedule: 0 17 * * 4` | Japanese notation cannot be parsed |
| `schedule: 9:00` | `schedule: 0 9 * * *` | HH:MM format is not a 5-field cron expression |
| `schedule: every 5 minutes` | `schedule: */5 * * * *` | English notation cannot be parsed |
| `schedule: 0 9 * * 7` | `schedule: 0 9 * * 6` | Weekday 7 is out of range (0-6) |
| `schedule: 0 9 * * SUN` | `schedule: 0 9 * * 6` | Weekday names cannot be used (numbers only) |
| `schedule: 0 25 * * *` | `schedule: 0 23 * * *` | Hour must be in the range 0-23 |
| `schedule: 60 * * * *` | `schedule: 0 * * * *` | Minute must be in the range 0-59 |
| `skip_pattern: ^\[\]$` (without quotes) | `skip_pattern: "^\[\]$"` | `[]` is interpreted as an empty list in YAML. Wrap it in quotes |

---

## Notes

- **Hot reload**: When `cron.md` / `heartbeat.md` is updated via Anima's `write_memory_file`, etc., the schedule change callback triggers `reload_schedule` and the job is re-registered immediately. Subordinate management files should also be edited with the write memory tool as in `../{anima_name}/cron.md`. External direct edits are also detected by the mtime check (`_check_schedule_freshness`) just before the next **heartbeat or any cron fires**, but this is not the standard procedure for supervisor edits to subordinate files
- **Old jobs immediately after reload**: When the scheduler is rebuilt upon detecting an mtime change, **cron firings tied to the previous definition may be skipped as "stale"** (intentional duplicate execution prevention)
- **Time zone**: APScheduler uses `get_app_timezone()`. You can set an IANA name (e.g., `Asia/Tokyo`) in `system.timezone` of `config.json`. When **empty**, the OS time zone is auto-detected, falling back to `Asia/Tokyo` on failure
- **Concurrency**: **If task names differ**, multiple jobs overlapping in the same minute may run in parallel via `asyncio.create_task`. The same task name will not re-enter while running (skipped via `_cron_running`). Each job is `max_instances=1`
- Command type does not stop the process on failure (`cron_executed` is recorded, and `stderr` / exit_code remain in the log). **The follow-up cron LLM runs only on success and when stdout exists** (as described above)
- For periodic execution of `type: llm`, a **background model** (`background_model` of `status.json`, etc.; the main model if not set) is used
- Detailed command output is accumulated in `state/cron_logs/` (daily JSONL) and housekept for up to 14 days
- **When accessing another Anima's tools/ directory, check permissions in advance**