# Canonical Task Architecture

## One Persistent Source of Truth

The canonical source for LLM tasks is the host-managed TaskStore. It atomically commits task IDs, complete execution inputs, dependencies, results, execution attempts, delegation aliases, and persistent wake-up notifications in the required units. It is not a configuration that cross-references separate file execution queues and supervisor ledgers.

Use `list_tasks` / `task_tracker` for verification, and `submit_tasks` / `delegate_task` / `update_task` for changes. Do not edit the database or task files directly. `backlog_task` registers tracking-only work and does not acquire execution rights.

## Execution Contract

1. A new `submit_tasks` atomically publishes the task and its complete inputs. It retains the original instruction, constraints, workspace, and completion conditions.
2. The host checks dependencies and acquires execution rights with a unique attempt token. Only the host sets `in_progress`.
3. The agent declares `done` / `pending` / `cancelled` via `update_task`. Old attempts cannot overwrite the completion or accepted results of new attempts.
4. The host handles dependency completion and persistent wake-ups, requiring no periodic Heartbeat. Cancellations, abnormal terminations, and interruptions leave an audit trail and a reason for required action.
5. Interrupted tasks are not blindly retried. After confirming completed operations and resolving the cause, explicitly resume the same unfinished task with `submit_tasks(..., tasks=[{"task_id": "ID", "resume": true}])`. Inputs and history are preserved. Redelivery without resume is idempotent.

The supervisor's delegation view is an alias to the subordinate's canonical task. It reflects the latest status on both sides without a separate mutable ledger or Heartbeat synchronization. Dependency completion does not necessarily mean success; do not treat a canceled task as done and trigger downstream work.

## Work Context and Audit Trail

`state/current_state.md` is a concise work context, not the canonical task. It holds observations, plans, and blockers, and is retained across normal session boundaries. Permanent knowledge and procedures are stored in dedicated memory areas.

The result summary of TaskExec is placed in `state/task_results/{task_id}/{attempt_token}.md`, and TaskStore selects the accepted result. File names or old summaries alone cannot prove completion. Activity logs and original instructions are kept as the audit trail.

## Legacy Storage and Command Tasks

The legacy `state/task_queue.jsonl` and `state/pending/` are retained solely as audit trails for migration and export. Migration is performed explicitly by operators after stopping legacy write operations and taking backups. Do not import live legacy data through arbitrary reads.

Long-running command tools are separate. `animaworks-tool submit` continues to use `state/background_tasks/pending/`, and BackgroundTaskManager stores command status and notifications. Do not remove this file path because of changes to LLM tasks.

See `reference/operations/task-management.md` for tool examples and `operations/background-tasks.md` for command execution.
