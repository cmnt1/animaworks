# Project Memory Update
## Scope and Protection Conditions

{anima_name}, please review only the new records below.

{episodes_summary}

Save only confirmed human instructions, customer-specific facts, and reusable environment-specific procedures or lessons. Keep PR SHAs, approval statuses, one-time results, and descriptions of general operations in the case history; do not expand long-term knowledge with them.

If there are items to save, use `search_memory` to search for existing related files, and read the original via `read_memory_file` before updating. Create new files only when no existing entry covers the item. Preserve source, date, and confidence level; do not turn speculation into fact, and do not mix details from different customers or cases.

Save original records, confirmed instructions, approval conditions, and important tags. `identity.md`, `injection.md`, automatic rewriting of permissions, and overall deduplication are not part of this task. If no changes are needed, rewrite nothing. Complete the task using memory operations only; do not use `delegate_task`, `submit_tasks`, or `send_message`.

After completion, briefly report only the files changed and the rationale.