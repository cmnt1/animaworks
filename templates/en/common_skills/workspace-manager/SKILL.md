---
name: workspace-manager
description: >-
  Configure the registration, listing, deletion, and assignment of workspaces (working directories).
  Use when: Use when: you need to link project paths to Anima, manage aliases, and switch working directories.
tags: [workspace, directory, project, management]
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and return only the translation without explanations.

Please provide the Japanese content you’d like me to translate.# Workspace Management

A skill for managing the project directory (workspace) where Anima works.## 概念

Animaは普段「自分の家」（~/.animaworks/animas/{name}/）にいる。
プロジェクトの作業をするときは「仕事場」（ワークスペース）に出かけて作業する。

ワークスペースは組織共有のレジストリ（config.json の workspaces セクション）に登録し、エイリアス#ハッシュで参照する。

## Aliases and Hashes

- Alias: A short name assigned by humans (e.g., `myproject`)
- Hash: Automatically assigned as the first 8 characters of the SHA-256 of the path (e.g., `3af4be6e`)
- Full form: `myproject#3af4be6e` — zero possibility of collision
- Tool arguments can use any of the following: alias only, full form, hash only, or absolute path## How to Use### Registration

A top-level Anima that has received an explicit instruction from a human uses `grant_workspace_access`:

```json
{
  "alias": "finance-dashboard",
  "path": "/absolute/path/to/project",
  "make_default": true
}
```

This tool handles registration in the organization shared registry, adding write permission to `permissions.json.file_roots`, and updating `status.json.default_workspace` as needed.

**Note**: An error occurs if the directory does not exist.
**Note**: `read_memory_file(path="config.json")` reads the `config.json` in its own Anima directory. It is not used for registration in the organization shared registry.### List

Check the list of organization shared registries at `core.org.workspace.list_workspaces()`. Do not use `read_memory_file(path="config.json")`.### Deletion

Deletion is treated as an administrator operation. In normal work, do not overwrite existing aliases; register new aliases instead.### Change your default workspace

Top-level Anima specifies `grant_workspace_access` in `make_default: true`.
Non-top-level Anima cannot add permissions themselves. Have a human give instructions to the top-level Anima.

Use when:### Assignment to Subordinates (For Supervisors)

A top-level Anima that has received explicit instructions from a human can grant permission to a subordinate or descendant Anima by specifying `target_anima`:

```json
{
  "alias": "finance-dashboard",
  "path": "/absolute/path/to/project",
  "target_anima": "ritsu",
  "make_default": true
}
```
## Usage in Tools

- **submit_tasks**: Specify an alias in the `workspace` field of each task
- **delegate_task**: Specify an alias in the `workspace` field## Notes

- The directory is checked for existence both at registration and at time of use
- Attempting to register a non-existent directory results in an error
- Overwriting an alias changes the hash, so references to the old hash will fail to resolve
- Humans do not need to remember hashes — aliases alone are sufficient