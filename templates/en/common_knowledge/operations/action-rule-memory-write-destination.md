## [ACTION-RULE] Memory Storage Location
trigger_tools: write_memory_file, create_skill
keywords: memory, writing, knowledge, procedures, skills, action-rule, current_state
---
- `knowledge/`: Facts, preferences, policies, judgments, lessons learned, and failure records
- `procedures/`: Reusable work procedures
- `skills/{name}/SKILL.md`: Reusable capabilities, tool workflows, and playbooks
- `knowledge/action-rule-*.md`: Rules to check immediately before operations with side effects
- `state/current_state.md`: Working memory for temporary observations, plans, and blockers only

For details, read `read_memory_file(path="reference/operations/memory-writing-guide.md")`.