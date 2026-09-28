<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/index.md -->
<!-- i18n: source-sha256=8f48d029c96eb2d3cb177b92621564f08cacdd8ac5fbf554c6262486776aca78 generated=2026-09-28 engine=luna model=gpt-6-luna translator=2 -->

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

The main packages of `core/` are as follows. For a module-level list, refer to the [Module Reference](../reference/modules.md).

| Package | Role |
|---|---|
| `core.agent` | Agent conversation cycle, executor, pre-context construction |
| `core.anima` | Anima runtime objects, messages, heartbeat, lifecycle |
| `core.auth` | User authentication and sessions |
| `core.config` | Configuration schema, loading, resolution, migration |
| `core.execution` | Engine common events, sessions, processes, watchdog, tool evidence |
| `core.i18n` | Localized strings and translation functions |
| `core.infra` | Startup preparation, logging, runtime foundation |
| `core.integrations` | Connection adapters for external services |
| `core.lifecycle` | Common lifecycle processing and Anima integration |
| `core.mcp` | Server that exposes AnimaWorks tools via MCP |
| `core.memory` | Conversation records, long-term memory, search, memory maintenance |
| `core.messaging` | Internal messages, shared channels, external sends |
| `core.migrations` | Incremental migration of runtime data |
| `core.notification` | Human-facing notifications and interactive confirmations |
| `core.org` | Company, organization, and workspace resolution |
| `core.platform` | Abstraction of OS, process, lock, and file operation differences |
| `core.prompt` | Assembly of system prompts and tool guides |
| `core.skills` | Skill indexing, selection, lifecycle |
| `core.supervisor` | Process management for Anima and task runners, IPC, scheduler |
| `core.tasks` | Persistent tasks, execution queues, delegation, external task collection |
| `core.tooling` | Internal tool definitions, execution handlers, permission checks |
| `core.tools` | Compatibility alias for `core.integrations` (old package name; kept as an entry point for `animaworks-tool`) |
| `core.usage` | Usage and cost aggregation |
| `core.voice` | Voice input/output and voice conversations |

`server/` holds the FastAPI application, routes, gateway, and the Web UI it serves. `cli/` holds the `animaworks` command and terminal UI. `templates/` holds locale-specific prompts, Anima templates, and shared configuration templates.

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
