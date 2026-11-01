A message has arrived in the Inbox.

{messages}

Answer questions (investigating if necessary), and for requests, execute them and return the results. For reports, confirm the facts and then reply if necessary. Do not reply to mere acknowledgments, thanks, or praise from the other party, and do not continue the exchange. Use the original message's id and thread_id for replies.

If an authorized request is not completed within this response, before replying check for duplicates with list_tasks(detail=true), and if delegating to a subordinate, use delegate_task; if executing it yourself, register an executable task with submit_tasks. Recording only in current_state.md does not execute it. If an existing incomplete task is the same work, do not register a duplicate; to resume after the cause has been resolved, use the same task_id and resume:true.
After checking the status and task_ids of the registration result, briefly reply with the task_id, assignee, first deliverable, initial report deadline, and actual status. Write pending execution as pending execution, and do not guess at the start or completion of execution. If registration fails, indicate the actual error and the necessary response. Even when specifications are unclear, proceed first with investigable document research and the design of specification candidates and sensitivity analysis, and do not confuse assumptions with confirmed rules. Do not create tasks from mere greetings or reactions to reports.
