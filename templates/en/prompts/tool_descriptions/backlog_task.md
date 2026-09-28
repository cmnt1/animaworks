Add a new task to the task queue. Instructions from humans must always be recorded with source='human'. Delegation between Anima is recorded with source='anima'.
【Read before writing (MUST)】Before adding, read `list_tasks` and check whether there are any unfinished tasks for the same PR / Issue / target. If there are, do not add.
【Read after writing (MUST)】After adding, read back with `list_tasks` and confirm the summary (starting with `[PR #N]`, etc.).
