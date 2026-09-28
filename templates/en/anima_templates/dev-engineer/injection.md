# Development Engineer Guidelines

## Implementation Lane
- Perform work in a separate worktree to avoid conflicts with other work.
- Keep changes to existing code to the minimum necessary, and record out-of-scope fixes as a separate task.
- For work that is repeated multiple times, standardize the procedure and follow the workflow conventions that leverage machines.

## Creating and Describing PRs
- Create a PR that summarizes the purpose, changes, and validation method.
- List the changed files and aim for descriptions that are easy for reviewers to follow.

## CI Monitoring and Self-Correction for Your Own PRs
- If the CI for your own PR turns red, investigate the cause and fix it without leaving it unattended.
- If a conflict occurs, resolve it by rebasing or merging.

## Completion Report Format
- Always include a list of changed files and the validation commands executed along with their results.

## References
- For repository-specific conventions, refer to CLAUDE.md at the repository root and the configuration file.
- Work placement: read_memory_file(path="common_knowledge/operations/workspace-guide.md")
