<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/index.md -->
<!-- i18n: source-sha256=d5f5c722e32a0301241507fea380830cb22ca5f7f0e766c2095ee93ab74f9881 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

> Confirmed commit: b304b7dc

# Architecture

AnimaWorks consists of a server that provides an HTTP API and Web UI, a supervisor that manages the processes of each Anima, a root process for each Anima, a task runner that is isolated per request, and multiple LLM execution engines. Memory search and updates, as well as task persistence, are handled through their respective shared boundaries.

```mermaid
flowchart TD
    UI[Web UI / CLI] <--> Server[server: API・WebSocket]
    Server --> Supervisor[Process Supervisor]
    Supervisor <-->|IPC: Unix socket / loopback TCP| Root[Anima root process]
    Root --> Scheduler[Scheduler・inbox dispatch]
    Root -->|IPC v2| Runner[分離された task runner]
    Runner -->|HTTP service URLs| Memory[記憶・ベクトルサービス]
    Root --> Memory
    Root --> Store[(Anima memory store)]
    Runner --> Engine[Execution 中間層]
    Engine --> Engines[Claude / Codex / Grok / Cursor / Gemini / LiteLLM]
    Memory --> Store
    Runner --> Tasks[(共有 TaskStore)]
    Server --> Tasks
```

## Repository Structure

The main packages in `core/` are as follows. For a module-by-module list, see the [Module Reference](../reference/modules.md).

| Package | Role |
|---|---|
| `core.agent` | Agent conversation cycle, executor, and pre-context construction |
| `core.anima` | Anima runtime objects, messages, heartbeat, and lifecycle |
| `core.auth` | User authentication and sessions |
| `core.config` | Configuration schemas, loading, resolution, and migration |
| `core.execution` | Engine-wide events, sessions, processes, watchdog, and tool evidence |
| `core.i18n` | Localized strings and translation functions |
| `core.infra` | Startup preparation, logs, and runtime infrastructure |
| `core.integrations` | External service integrations and animaworks-tool implementations |
| `core.lifecycle` | Common lifecycle processing and Anima integration |
| `core.mcp` | Server that exposes AnimaWorks tools via MCP |
| `core.memory` | Conversation records, long-term memory, search, and memory maintenance |
| `core.messaging` | Internal messages, shared channels, and outbound messages |
| `core.migrations` | Incremental migration of runtime data |
| `core.notification` | Human-facing notifications and interactive confirmations |
| `core.org` | Resolution of company, organization, and workspace |
| `core.platform` | Abstraction of OS, process, lock, and file operation differences |
| `core.prompt` | Assembly of system prompts and tool guides |
| `core.skills` | Skill indexing, selection, and lifecycle |
| `core.supervisor` | Process management, IPC, and scheduler for Anima and the task runner |
| `core.tasks` | Persistent tasks, execution queue, delegation, and external task collection |
| `core.tooling` | Internal tool definitions, execution handlers, and permission checks |
| `core.usage` | Usage and cost aggregation |
| `core.voice` | Audio input and output, and voice conversations |

`server/` contains the FastAPI application, routes, gateway, and the Web UI it serves. `cli/` contains the `animaworks` command and terminal UI. `templates/` contains locale-specific prompts, Anima templates, and shared configuration templates.

## Runtime Data

The default data root is `~/.animaworks/`. It can be changed via the environment variable `ANIMAWORKS_DATA_DIR` or the CLI option `--data-dir`. The code resolves the root and its subpaths through `core/paths.py`.

| Path | Purpose |
|---|---|
| `config.json` | Application-wide configuration |
| `models.json` | Additional model name patterns and per-model metadata |
| `permissions.global.json` | Common permission constraints applied to all Anima |
| `animas/{name}/` | Per-Anima configuration, memory, and status. See [Anima Files](anima-files.md) for details |
| `shared/` | Data shared across multiple Anima, such as inbox, shared channels, and TaskStore |
| `common_knowledge/` | Knowledge materials shared between Anima |
| `common_skills/` | Common skills |
| `logs/` | Logs for server, Anima, and task runners |

The authoritative source for each Anima's per-anima configuration is `status.json`; for the meaning of model-related keys, refer to the [Configuration Reference](../reference/config.md). This chapter does not enumerate all configuration keys.
