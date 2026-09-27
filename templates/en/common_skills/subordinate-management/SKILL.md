---
name: subordinate-management
description: >-
  Supervisor operations for the Anima subordinate. Perform suspension, resumption, model changes, restart, task delegation, status reading, and auditing.
  Use when: Use when: you need to disable or re-enable a subordinate, change the main or BG model, restart a process, delegate a task, or check the organization dashboard.
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and translate only exposed values in the frontmatter. Please provide the content you’d like me to translate.# Skill: Subordinate Management (Supervisor Tools)

A set of supervisor tools that are automatically enabled for Anima with subordinates. These tools manage the suspension, resumption, model changes, background model changes, restarts, and status checks of all subordinates (children, grandchildren, great-grandchildren, etc.), as well as task delegation and progress tracking for direct subordinates.## Available Tools### Operable on All Subordinates (Children, Grandchildren, Great-Grandchildren, etc.)

| Tool | Purpose |
|------|---------|
| `disable_subordinate` | Suspend subordinates (status.json `enabled: false` → process shutdown + prevent automatic recovery) |
| `enable_subordinate` | Resume suspended subordinates |
| `set_subordinate_model` | Change subordinate's main LLM model (status.json update. `restart_subordinate` required for the change to take effect) |
| `set_subordinate_background_model` | Change subordinate's background model (for heartbeat/cron) (status.json update. `restart_subordinate` required for the change to take effect. Use empty string to clear) |
| `restart_subordinate` | Restart subordinate process (status.json `restart_requested` flag. Reconciliation will restart within approximately 30 seconds) |
| `delegate_task` | Delegate tasks to direct subordinates (queue addition + DM send + create tracking entry on own side) |
| `org_dashboard` | Display tree of process status, last activity, current task, and task count for all subordinates |
| `ping_subordinate` | Check subordinate liveness (`name` omitted for batch check of all, specified for individual) |
| `read_subordinate_state` | Read subordinate's `current_state.md` |
| `audit_subordinate` | Comprehensive audit of subordinate's recent activity (activity summary, task status, error frequency, tool usage statistics, communication patterns) |### Delegated Task Tracking

| Tool | Purpose |
|------|---------|
| `task_tracker` | Track the progress of tasks delegated via `delegate_task` from the subordinate's queue (`status`: all / active / completed. Default: active) |

The tracking card from the delegating side references the authoritative task record of the delegatee. Use `task_tracker` to check the status.## Important: Difference between disable_subordinate and send_message

- **disable_subordinate**: Changes status.json to `enabled: false`. Reconciliation will not automatically recover. **Use this one**
- Merely sending a "take a rest" message via send_message will **not stop the process**. Even if a message is sent, Reconciliation will restart## How to Use### Suspension and Resumption

When suspending multiple people, call `disable_subordinate` for each person individually:

```
disable_subordinate(name="aoi", reason="業務縮小のため一時休止")
disable_subordinate(name="taro", reason="業務縮小のため一時休止")
enable_subordinate(name="aoi")
```
### Model Change and Restart

Model changes are saved to status.json, but `restart_subordinate` is required to apply them to running processes:

```
set_subordinate_model(name="aoi", model="claude-sonnet-4-6", reason="負荷分散のため")
restart_subordinate(name="aoi", reason="モデル変更を反映")
```

When changing the background model (for heartbeat/cron):

```
set_subordinate_background_model(name="aoi", model="claude-sonnet-4-6", reason="heartbeat負荷軽減")
restart_subordinate(name="aoi", reason="バックグラウンドモデル変更を反映")
```

To clear the background model and revert to the main model:

```
set_subordinate_background_model(name="aoi", model="", reason="メインモデルに統一")
restart_subordinate(name="aoi")
```
### Status Verification and Audit

```
org_dashboard()                         # 配下全体のダッシュボード
ping_subordinate()                      # 全配下の生存確認
ping_subordinate(name="aoi")            # 単一の生存確認
read_subordinate_state(name="aoi")      # 現在タスク・保留タスクの内容
audit_subordinate(name="aoi")           # 直近1日の包括監査レポート
audit_subordinate(name="aoi", days=7)   # 直近7日間の監査（days は 1〜30）
audit_subordinate(since="09:00")        # 全配下の今日9時以降の監査
audit_subordinate(name="aoi", since="13:00")  # aoi の今日13時以降
```

Can also be executed from the CLI (useful when used via Bash in S/C/D/G-mode):

```bash
animaworks anima audit aoi              # 直近1日の監査
animaworks anima audit aoi --days 7     # 直近7日間の監査
animaworks anima audit --all --since 09:00  # 全Anima、今日9時以降
```
### Task Delegation

```
delegate_task(name="aoi", instruction="週次レポートをまとめて", summary="週次レポート作成")
# 必須: `name`, `instruction`。任意: `summary`, `workspace`, `acceptance_criteria`, `model`
# workspace を指定すると委譲先がそのワークスペースで作業する（workspace-manager スキル参照）
task_tracker(status="active")      # 委譲タスクの進捗確認（status: all / active / completed）
```

For assigning workspaces to subordinates (specifying the main working directory), refer to the `workspace-manager` skill.## Permission

- **All subordinates (children, grandchildren, great-grandchildren… recursively)**: Status confirmation and management tools are available
- **Direct subordinates only**: `delegate_task` (task delegation)
- Operations on oneself are not permitted