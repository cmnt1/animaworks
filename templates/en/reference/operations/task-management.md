# How to Manage Tasks

## There Is Only One Source of Truth

Use `list_tasks(detail=true)` or `animaworks-tool task list` for confirmation. Persist instructions, dependencies, execution attempts, results, and delegation aliases in the host-managed TaskStore. Directly editing the database, fabricating execution rights, and repairing the queue by writing files are prohibited. The old `state/task_queue.jsonl` and `state/pending/` are evidence for migration and export, and are not active submission destinations. They are retained for migration by the operator.

Requests that can be handled in normal chat may be handled directly. Register a task only when background execution, parallelization, or continuous tracking is required. Human-originated requests have the highest priority, and when priorities are equal, prioritize a supervisor's request over a colleague's. In handoffs, preserve the original instruction, completion conditions, constraints, and necessary context.

## Choose the Execution Path

- Inbox processes messages and lightweight replies.
- Heartbeat checks for meaningful changes and decides how to respond. Do not perform long coding sessions or large numbers of tool executions, and use `submit_tasks` for your own TaskExec and `delegate_task` for direct subordinates.
- TaskExec executes persisted tasks with tools. The host manages acquisition of execution rights, parallelism, dependencies, cancellation, and recovery of attempts, and it does not depend on periodic Heartbeat.
- The subagent startup tool for Agent/Task is disabled. Use the submission and delegation tools above.

## Submission and Confirmation

The executor of `submit_tasks` is not a subordinate but **your own TaskExec**.

```
submit_tasks(batch_id="report-build", tasks=[
  {"task_id": "collect", "title": "根拠収集", "description": "依頼された根拠を出典付きで収集する。", "parallel": true},
  {"task_id": "report", "title": "報告作成", "description": "収集結果から依頼された報告書を作る。", "depends_on": ["collect"]}
])
list_tasks(detail=true)
```

A new task requires `task_id`, `title`, and `description`. Optional items are `context`, `acceptance_criteria`, `constraints`, `file_paths`, `workspace`, `parallel`, `depends_on`, `reply_to`, and `model`. `workspace` is an alias for a registered workspace. Model selection follows normal runtime configuration. Do not replace a long original instruction with a short summary.

Validate the batch at submission time and finalize the task and execution input all at once. Redelivery of the same submission is idempotent and is not a retry. Subsequent tasks are not executed until the dependency completes successfully. Do not judge that execution is possible based only on the absence of a file or the display of `pending`.

## Result Declaration and Explicit Resumption

```
update_task(task_id="TASK_ID", status="done", summary="検証済みの結果", result="根拠と成果物の場所")
update_task(task_id="TASK_ID", status="pending", summary="指定した入力を待っている")
update_task(task_id="TASK_ID", status="cancelled", summary="不要になった理由")
```

`in_progress` is a viewing status set by the host when execution rights are acquired. Do not set it with `update_task`. A task whose attempt ended without a completion declaration may become pending with a reason requiring action. Pending is not a promise of automatic retry. Do not duplicate it with a different ID in order to resume it.

After resolving the reason for the interruption, explicitly resume the same unfinished task.

```
submit_tasks(batch_id="resume-report", tasks=[{"task_id": "TASK_ID", "resume": true}])
```

Reuse the saved input and preserve the history. An active attempt cannot be resumed, and completed or canceled tasks cannot be resumed this way either. If a dependency is canceled or requires action, check the details and either confirm with the requester or cancel the work that is no longer needed. Do not fabricate success.

When you cannot proceed, tell the requester the facts, what you tried, the missing permissions or information, and the next step, and do not repeat the same failure. Search related knowledge when necessary, and do not turn it into a ritual. While waiting, you may work on other permitted work. Report completion of delegated work to the requester, and avoid duplicate notifications and unnecessary acknowledgment replies.

## Delegation to Subordinates

```
delegate_task(name="dave", instruction="API テストを実施し検証した結果を報告する", summary="API テスト")
task_tracker()
```

Create one task owned by the subordinate and an alias visible to the supervisor. The same latest status is immediately reflected for both, and separate ledgers or Heartbeat synchronization are unnecessary. `task_tracker(status="all")` includes completed ones, and `status="completed"` displays done/cancelled. If the instruction is unclear, confirm with the delegation source, and report the result upon completion.

## Work Context and Results

In `state/current_state.md`, briefly leave observations, context, plans, and blockers. Do not place duplicates of the task list or permanent procedures there. If there is no work context, `status: idle`. It is retained across normal session boundaries, and display limits and disk cleanup limits are separate (`anatomy/working-memory.md`).

The result summary of TaskExec is saved in `state/task_results/{task_id}/{attempt_token}.md`. Pass the result of the attempt accepted by the host to subsequent steps, and do not arbitrarily adopt old files. Fabricating result files and determining completion based only on their existence are prohibited. Activity logs and episodes remain as evidence, and there is no obligation to manually double-record each status transition.

## Long-Running Command Tools Use a Separate Path

For long-running external tools such as image generation and run_command, use `animaworks-tool submit TOOL ...`. They are registered as `task_type="command"` in the same TaskStore as the LLM tasks of `submit_tasks`, and are executed by BackgroundTaskManager. Execution attempts are recorded in the TaskStore, and for compatibility `state/background_tasks/{task_id}.json` and completion notifications are also maintained. Check results with `list_background_tasks` / `check_background_task`. For details, see `operations/background-tasks.md`.

## Source of Truth for Business Deliverables

Place the source of truth for business deliverables and case management in the Obsidian Vault. Follow `common_skills/obsidian-product/SKILL.md`, and Anima's internal TaskStore manages execution status and dependencies. Preserve the roles of both, and do not write a duplicate of the execution queue into the Vault.
