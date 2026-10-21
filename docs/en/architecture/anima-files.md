<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/anima-files.md -->
<!-- i18n: source-sha256=daf64ea97e7848803fe9645eef09e595a1a72796660b7750b35fbc74b1896fc6 generated=2026-10-21 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

> Confirmed commit: b304b7dc

# Anima files

Each Anima has a directory at `~/.animaworks/animas/{name}/`. Personality, behavioral guidelines, and runtime configuration are stored separately in text and JSON, while information updated during a session is placed in `state/`.

## Definition and configuration

| File | Role |
|---|---|
| `identity.md` | Describes Anima's persistent personality, such as character, speaking style, and self-introduction. |
| `injection.md` | Describes expertise and additional behavioral guidelines, incorporated into the system prompt. |
| `permissions.json` | Represents permissions for tools, commands, and file access for individual Anima instances. |
| `status.json` | Holds per-anima information resolved at runtime, such as enabled status, role, assignment, model, authentication, supervisor, and heartbeat activation. |
| `heartbeat.md` | Describes heartbeat instructions and active time windows. The execution interval is determined by global configuration or the value of `status.json`, and is not set from the body of this file. |
| `cron.md` | Describes periodically executed tasks under each heading. The supervisor reads the schedule and execution content. |

`status.json` is the authoritative source for per-anima values related to ModelConfig. See the [configuration reference](../reference/config.md) for the list of corresponding keys and default values. `permissions.json` and the global `permissions.global.json` are used for permission decisions. See [security](../security.md) for permission boundaries and evaluation methods.

## Runtime Status

| Path | Role |
|---|---|
| `state/current_state.md` | Working state that holds ongoing work, decisions, next steps, and so on. It is incorporated into the prompt as needed, and updates are protected by a lock for the state file. |
| `state/task_queue.jsonl` | Migration input used when legacy task data remains. The source of truth for current tasks is the shared SQLite TaskStore; do not treat this file as a separate runtime queue. |
| `state/background_tasks/` | Stores the status and results of background processes started at `animaworks-tool submit`. Completion results are notified or referenced in conversations and by subsequent background runs. |
| `scratch/` | A disposable workspace. Child processes receive either a task-specific `scratch/task-<id>/` or a session-type-specific `scratch/<種類>/` as `ANIMAWORKS_SCRATCH_DIR`. Task-specific workspaces are deleted when the task is completed or canceled; all others are deleted by housekeeping after 24 hours of inactivity. |

Anima’s long-term memory, conversation history, skills, and other resources are organized into subdirectories by purpose. For details about memory, see the relevant sections of `docs/ja/memory/`.

## Design decisions

- **Memory is held in Markdown files.** AI can read and write them naturally, and they work well with grep. JSON is limited to configuration and status.
- **Archive-style memory is adopted.** Truncation-style memory that packs the latest N items into the prompt has a limit on memory capacity. With archive-style memory that searches and recalls what is needed, memory can continue to grow.
- **Permissions are a limitation of visibility.** Because there are things one does not know, one asks others. If everyone can see everything, the organization loses its meaning.
