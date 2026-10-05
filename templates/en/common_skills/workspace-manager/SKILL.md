---
name: workspace-manager
description: >-
  Registers, lists, removes, and assigns workspaces (project directories) for Anima work.
  Use when: binding project paths to Anima, managing aliases, or switching workspace roots.
tags: [workspace, directory, project, management]
---


# Workspace Management

Skill for managing project directories (workspaces) where Animas perform work.

## Concept

Anima is usually at “its own home” (~/.animaworks/animas/{name}/）).
When working on a project, it goes to the “workplace” (workspace) to work.

Workspaces are registered in the organization-shared registry (the workspaces section of config.json) and referenced as alias#hash.

## Aliases and Hashes

- Alias: A short name assigned by humans (e.g., `myproject`)
- Hash: The first 8 hex digits of the path's SHA-256, auto-generated (e.g., `3af4be6e`)
- Qualified form: `myproject#3af4be6e` — zero collision risk
- Tool arguments accept alias only, qualified form, hash only, or absolute path

## Operations

### Registration

A top-level Anima that has received explicit instruction from a human uses `grant_workspace_access`:

```json
{
  "alias": "finance-dashboard",
  "path": "/absolute/path/to/project",
  "make_default": true
}
```

This tool requests the root host to update the organization-shared registry and the root-owned `permissions.json` / `status.json`. Do not write configuration files directly from the Anima process.

**Note**: An error occurs if the directory does not exist.
**Note**: `read_memory_file(path="config.json")` reads the `config.json` in its own Anima directory. It is not used for registering in the organization-shared registry.

### List

Use `core.org.workspace.list_workspaces()` to inspect the shared registry. Do not use `read_memory_file(path="config.json")`.

### Remove

Treat removal as an administrator operation. For normal work, avoid overwriting an existing alias and register a new alias instead.

### Change Your Default Workspace

A top-level Anima sets `make_default: true` when calling `grant_workspace_access`.
Non-top-level Animas cannot grant themselves workspace access; ask the top-level Anima via a human instruction.

### Assign to Subordinates (for Supervisors)

A top-level Anima with an explicit human instruction can grant access to a subordinate or descendant by setting `target_anima`:

```json
{
  "alias": "finance-dashboard",
  "path": "/absolute/path/to/project",
  "target_anima": "ritsu",
  "make_default": true
}
```

## Tool Usage

- **submit_tasks**: Specify alias in each task's `workspace` field
- **delegate_task**: Specify alias in the `workspace` field

## Notes

- Directories are validated both at registration and at resolution time
- Attempting to register a non-existent directory results in an error
- Overwriting an alias changes the hash, so old hash references will fail to resolve
- Humans don't need to remember hashes — alias alone is sufficient
