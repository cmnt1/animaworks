# Task Management Methods

## There is only one source of truth

Use `list_tasks(detail=true)` or `animaworks-tool task list` for confirmation. Persist instructions, dependencies, execution attempts, results, and delegation aliases in the host-managed TaskStore. Direct database edits, fabricating execution permissions, and repairing queues by writing files are prohibited. The old `state/task_queue.jsonl` and `state/pending/` are evidence for migration and export, not active submission targets. They are kept for operator-driven migration.

Requests that can be handled in normal chat may be addressed directly. Register a task only when background execution, parallelization, or continuous tracking is needed. Prioritize human-originated requests; among equal priorities, prioritize supervisor requests over colleague requests. In handovers, preserve the original instruction, completion conditions, constraints, and necessary context.

## Choose the execution path

- Inbox handles messages and lightweight replies.
- Heartbeat checks for meaningful changes and decides how to respond. Do not engage in long coding sessions or heavy tool use; use `submit_tasks` for your own TaskExec and `delegate_task` for direct subordinates.
- TaskExec executes persisted tasks with tools. The host manages permission acquisition, parallelism, dependencies, cancellation, and recovery of attempts, and does not rely on periodic Heartbeat.
- The subagent startup tool in Agent/Task is disabled. Use the submission and delegation tools above.

## Submission and confirmation

The executor of `submit_tasks` is **your own TaskExec**, not a subordinate.

```
submit_tasks(batch_id="report-build", tasks=[
  {"task_id": "collect", "title": "根拠収集", "description": "依頼された根拠を出典付きで収集する。", "parallel": true},
  {"task_id": "report", "title": "報告作成", "description": "収集結果から依頼された報告書を作る。", "depends_on": ["collect"]}
])
list_tasks(detail=true)
```

New tasks require `task_id`, `title`, and `description`. Optional fields are `context`, `acceptance_criteria`, `constraints`, `file_paths`, `workspace`, `parallel`, `depends_on`, `reply_to`, and `model`. `workspace` is an alias for a registered workspace. Model selection follows the usual runtime configuration. Do not replace a long original instruction with a short summary.

Validate the batch at submission and finalize tasks and execution inputs together. Redelivery of the same submission is idempotent, not a retry. Dependents are not executed until the dependency completes successfully. Do not judge executability based solely on file absence or the `pending` display.

## Result declaration and explicit resumption

```
update_task(task_id="TASK_ID", status="done", summary="検証済みの結果", result="根拠と成果物の場所")
update_task(task_id="TASK_ID", status="pending", summary="指定した入力を待っている")
update_task(task_id="TASK_ID", status="cancelled", summary="不要になった理由")
```

`in_progress` is a read-only status set by the host when execution permission is acquired. It is not set via `update_task`. Tasks whose attempts ended without a completion declaration may become pending with a reason requiring action. Pending is not a promise of automatic retry. Do not duplicate under a different ID to resume.

After resolving the interruption reason, explicitly resume the same unfinished task.

```
submit_tasks(batch_id="resume-report", tasks=[{"task_id": "TASK_ID", "resume": true}])
```

Reuse saved inputs and preserve history. Active attempts cannot be resumed, and completed or canceled tasks cannot be resumed this way. If a dependency is canceled or requires action, check the details, confirm with the requester, or cancel work that is no longer needed. Do not fabricate success.

When you cannot proceed, report the facts, what you tried, missing permissions or information, and the next step to the requester, and do not repeat the same failure. Search related knowledge only when necessary; do not ritualize it. While waiting, you may work on other permitted tasks. Report completion of delegated work to the requester, and avoid duplicate notifications or unnecessary acknowledgment replies.

## Delegation to subordinates

```
delegate_task(name="dave", instruction="API テストを実施し検証した結果を報告する", summary="API テスト")
task_tracker()
```

Create one task owned by the subordinate and an alias visible to the supervisor. The same latest state is immediately reflected on both sides; no separate ledger or Heartbeat synchronization is needed. `task_tracker(status="all")` includes completed items, and `status="completed"` displays done/cancelled. If instructions are unclear, confirm with the delegator, and report results upon completion.

## Work context and results

Record observations, context, plans, and blockers concisely in `state/current_state.md`. Do not place copies of task lists or permanent procedures there. If there is no work context, use `status: idle`. It is preserved across normal session boundaries; display limits and disk cleanup limits are separate (`anatomy/working-memory.md`).

The result summary of TaskExec is stored in `state/task_results/{task_id}/{attempt_token}.md`. Pass the results of host-accepted attempts to dependents, and do not arbitrarily adopt old files. Fabricating result files or declaring completion based solely on existence is prohibited. Activity logs and episodes remain as evidence; there is no obligation to manually double-record each state transition.

## Long-running command tools use a separate path

For long-running external tools such as image generation and run_command, use `animaworks-tool submit TOOL ...`. They are registered as `task_type="command"` in the same TaskStore as the `submit_tasks` LLM tasks, and are executed by BackgroundTaskManager. Execution attempts are recorded in TaskStore, and for compatibility, `state/background_tasks/{task_id}.json` and completion notifications are also maintained. Check results with `list_background_tasks` / `check_background_task`. For details, see `operations/background-tasks.md`.
