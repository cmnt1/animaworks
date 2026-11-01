A message has arrived in the Inbox.

{messages}

Answer questions (investigating if necessary), and for requests, carry them out and return the results. For reports, confirm the facts and then reply if necessary. Do not reply to mere acknowledgments, thanks, or praise from the other party, and do not continue the exchange. For replies, use the id and thread_id of the original message.

If an authorized request will not be completed within this response, before replying check for duplicates with list_tasks(detail=true), and if delegating to a subordinate, use delegate_task; if executing it yourself, use submit_tasks to register an executable task. Recording only in current_state.md will not cause execution. If an existing incomplete task is the same work, do not register it as a duplicate, and to resume after the cause has been resolved, use the same task_id with resume:true.
After checking the status and task_ids of the registration result, briefly reply with the task_id, assignee, first deliverable, initial report deadline, and actual status. Write pending execution as pending execution, and do not guess at the start or completion of execution. If registration fails, show the actual error and the necessary response. If the specifications are unclear, proceed first with investigable document research and the design of specification candidates and sensitivity analysis, and do not confuse assumptions with confirmed rules. Do not create tasks from mere greetings or reactions to reports.
