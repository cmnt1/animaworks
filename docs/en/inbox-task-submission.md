<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/inbox-task-submission.md -->
<!-- i18n: source-sha256=80ab667f58d4c9d8b5d2766739d2c5ea1c83000ca891481342a035bb236bb81e generated=2026-10-21 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# Connect requests received in Inbox to execution tasks

## Scope and preconditions

This applies to investigations, validation, and work that users have authorized and that arrive in Inbox from Discord or similar.
`inbox` and `inbox:<sender>` expose `submit_tasks`.
They are not exposed in TaskExec (`task:*`), normal chat, cron, or consolidation.
The prohibition on creating child tasks from TaskExec is also maintained.

## Steps Anima performs

1. Read the original request and necessary records, and check existing work with `list_tasks(detail=true)`.
   Even if the list is empty, it does not necessarily mean past validation has not been performed. Also check completed deliverables.
2. Work that finishes within a response is performed directly. Authorized work that requires continuation is turned into an executable task by passing a unique `batch_id` and `tasks` to `submit_tasks`.
   Do not stop after merely writing a note in `current_state.md` or registering it in a tracking ledger.
3. Include in the task the original text, purpose, inputs and existing deliverables, first deliverable, completion conditions, constraints, initial report deadline, and report destination. If the specification is not yet fixed, proceed from document investigation, explicitly stated assumptions, and the design of sensitivity analysis, and do not confuse assumptions with confirmed rules for actual operation.
4. After checking `status: submitted` and `task_ids`, report acceptance.
   Show the ID, assignee, first deliverable, and initial report deadline, and if startup has not been confirmed, write "registered, awaiting execution."
   If registration fails, report the actual error. Do not conclude "cannot register" without trying the available tools.
5. Do not duplicate-register existing unfinished tasks. Only when the reason for suspension has been resolved, resume with the same `task_id` and `resume:true`. If additional validation is requested for an analysis that is already complete, create a follow-up task that references the previous deliverable and ID.
6. Report the result or blocker to the original thread. Since the final Inbox response is sent automatically, do not double-post the same acceptance message with the send tool. Specify TaskExec's follow-up report destination in the task body.

## Operator validation steps

- Regression check for tool exposure:
  `.venv/Scripts/python.exe -m pytest tests/unit/core/tooling/test_submit_tasks_trigger_gate.py tests/unit/core/tooling/test_tool_surface_matrix.py tests/unit/core/test_mcp_server.py tests/unit/execution/test_sdk_hooks_agent_intercept.py tests/unit/core/test_submit_drain_integration.py -q`
- If an existing Anima process retains the old module, confirm that no tasks are running, then restart only the target Anima with `POST /api/animas/<name>/restart`.
  Restarting the entire server is unnecessary.
- Deliver an explicitly authorized request to Inbox, and check the person's `submit_tasks` call and `status: submitted` in activity_log. A task registered on the person's behalf by an operator does not verify the person's own registration capability.
- Check the attempt's `started_at` with `animaworks task show <id> --json`.
  Check `in_progress`, the deliverable, and follow-up reports respectively, and do not confuse successful registration with completed validation.
- `state/task_queue.jsonl` and `state/pending/` are old migration evidence. Do not directly edit or reinsert them.

## Cause on 2026-10-21

rika's action rules required registration, while the shared tool policy excluded `submit_tasks` in Inbox, and the Inbox common prompt also prohibited its use.
The tool exposure and the Japanese, English, and Korean common prompts were aligned and fixed.
Do not make CLI bypass execution a normal procedure; register with the official tool.

In the live check, the operator passed the original request text to rika's Inbox, and the person's `submit_tasks` call and `status: submitted` were confirmed at 2026-10-21 12:23:09 JST.
The follow-up ID is `rotation-followup-20261021`, and the batch is `rika-rotation-20261021`.
The start of the first attempt was also confirmed with task show. Unlike the previous proxy registration by the operator, this time rika herself, who handles the Inbox response, registered it. It was confirmed with an operator message to the same Inbox processing system, without spoofing a new Discord Gateway event.
The initial report deadline is within 60 minutes of registration (13:23 JST). Since this ID is actual validation preparation work, do not re-register the same work for an operation check.
