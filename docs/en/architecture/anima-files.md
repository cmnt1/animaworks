<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/anima-files.md -->
<!-- i18n: source-sha256=4058b5992b84f0303184a18c77cce99d86e2e702820420c335ccde9d598710f8 generated=2026-10-06 engine=luna model=gpt-6-luna translator=2 -->

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

## Runtime status

| Path | Role |
|---|---|
| `state/current_state.md` | Holds work status such as ongoing tasks, decisions, and next steps. It is incorporated into the prompt as needed, and updates are protected via a lock for status files. |
| `state/task_queue.jsonl` | Migration input when legacy task data remains. The authoritative source for current tasks is the shared SQLite TaskStore, and this file is not treated as a separate runtime queue. |
| `state/background_tasks/` | Stores the status and results of background processes started at `animaworks-tool submit`. Completion results are notified and referenced from conversations and subsequent background executions. |

Anima's long-term memory, conversation history, skills, and other data are organized into purpose-specific subdirectories. See the chapters in `docs/ja/memory/` for details on memory.

## Design decisions

- **Memory is held in Markdown files.** AI can read and write them naturally, and they work well with grep. JSON is limited to configuration and status.
- **Archive-style memory is adopted.** Truncation-style memory that packs the latest N items into the prompt has a limit on memory capacity. With archive-style memory that searches and recalls what is needed, memory can continue to grow.
- **Permissions are a limitation of visibility.** Because there are things one does not know, one asks others. If everyone can see everything, the organization loses its meaning.
