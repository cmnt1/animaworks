# Task Submission and Delegation
## Execution Path

Do not use the native sub-agent startup of Agent/Task; use the publicly available task tools instead.
Work that can be completed in normal chat should be executed directly. For continuous tracking only, use `backlog_task`,
for your own background execution use `submit_tasks`, and for delegation to an active direct subordinate use
`delegate_task(name="担当名", instruction="原指示と完了条件", summary="要約")`.
Follow the tools' provided scope and permissions; do not delegate to invalid assignees or switch to another path without authorization.
Use Heartbeat for judgment and submission; pass long-running actual work to TaskExec.
## Information to Hand Over

The executor does not automatically share conversation history. Provide the original instruction, purpose, relevant files and their known locations,
current status, completion conditions, approval conditions, and prohibitions. Do not fabricate paths or line numbers that do not exist.
Use `description`, `context`, `acceptance_criteria`, `constraints`, and `file_paths` as appropriate for the purpose.
Also preserve the model and registered workspace specifications. Do not instruct writing to another Anima's personal directory.

`submit_tasks(batch_id="work", tasks=[{"task_id":"job","title":"仕事","description":"具体的な依頼"}])`
publishes tasks and execution inputs in bulk. Resending the same ID is not re-execution.
`parallel:true` can run in parallel within the worker count limit; `depends_on` waits for the completion and trial termination of preceding tasks.
If a dependency is canceled or incomplete, confirmation is required; do not assume it succeeded.
## Status, Results, and Resumption

Check status via `list_tasks(detail=true)` and delegation tracking via `task_tracker()`.
The tracking ID is an alias for the same task owned by the subordinate; no ledger synchronization or file recovery is needed.
`task_tracker(status="all")` covers all items, `status="completed"` covers done/cancelled。
execution permission, and `in_progress` is managed by the host. Results are declared with evidence-based `done`,
`pending` with specific waiting reasons, and explicit cancellation via `cancelled`.

Upon receiving an incomplete notification, check already-completed external operations and outcomes, and only when continuation is appropriate,
reuse saved inputs via `submit_tasks(batch_id="resume-job", tasks=[{"task_id":"job","resume":true}])`.
Running, completed, or canceled work cannot be resumed this way. Do not resubmit indefinitely.
Result summary is `state/task_results/{task_id}/{attempt_token}.md`. Do not treat file existence alone as completion.
## Duplicates and Reporting

If you know there is incomplete work for the same request, pass additional information to that ID.
Do not automatically cancel or overwrite old work based only on suspected duplication; verify the assignee and execution status.
Preserve required approvals and independent reviews. Report results to the requester who needs to make decisions; do not require
forwarding the same content to all levels or double-recording in a separate handwritten ledger.
See `common_knowledge/anatomy/task-architecture.md` for storage details.