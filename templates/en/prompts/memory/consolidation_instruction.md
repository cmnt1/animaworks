# Project Memory Update

## Scope and Protection Conditions

{anima_name}, please review only the following new records.

{episodes_summary}

Only save confirmed human instructions, customer-specific facts, and reusable environment-specific procedures and lessons learned. Keep PR SHAs, approval statuses, one-time results, and descriptions of general operations in the case history; do not add them to long-term knowledge.

If there are items to save, search for existing related files with `search_memory`, and read the original with `read_memory_file` before updating. Create new files only when no existing entry covers the item. Preserve the source, date, and confidence level; do not turn speculation into fact, and do not mix details from different customers or cases.

Save original records, confirmed instructions, approval conditions, and important tags. Automatic rewriting of `identity.md`, `injection.md`, permissions, or overall deduplication is not part of this task. If no changes are needed, rewrite nothing. Complete this with memory operations only; do not use `delegate_task`, `submit_tasks`, or `send_message`.

After completion, briefly report only the files changed and the rationale.
