# Digital Anima Requirements Specification v1.1

## 1. Overview

Digital Anima is the minimal unit that encapsulates an AI agent as "a single person."

**Core Design Principles:**

- Internal state is invisible from the outside. The only external interface is text conversation
- Memory is "archive-based." The agent searches for and retrieves only the memories it needs, when it needs them
- Full context is never shared. Information is compressed and interpreted in the agent's own words before communicating
- Heartbeats enable proactive behavior rather than waiting for instructions
- Roles and principles are injected later. Digital Anima itself is an "empty vessel"

**Technical Direction:**

- Agent execution operates in **4 modes**: **S** (Claude Agent SDK — session management delegated to SDK), **A** (Anthropic SDK / LiteLLM + tool_use), **B** (one-shot assisted), **C** (Codex CLI wrapper)
- Configuration is unified in **config.json** (Pydantic validation); memories are written in **Markdown**
- Multiple Animas operate collaboratively in a **hierarchical structure** (hierarchy defined by the `supervisor` field, synchronous delegation)

-----

## 2. Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Digital Anima                      │
│                                                       │
│  Identity ──── Who I am (always resident)             │
│  Agent Core ── 4 execution modes                     │
│    ├ S: Claude Agent SDK (session delegated to SDK)   │
│    ├ A: Anthropic SDK / LiteLLM + tool_use            │
│    │  (Claude, GPT-4o, Gemini, etc., autonomous)     │
│    ├ B: One-shot assisted (Ollama, etc., FW-managed)  │
│    └ C: Codex CLI wrapper (execution via Codex)        │
│  Memory ───── Archive-based long-term memory          │
│    ├ Conversation memory (state/conversation.json, rolling compression)│
│    ├ Short-term memory (shortterm/chat/ and heartbeat/ separated)│
│    └ Unified activity log (activity_log/, JSONL timeline)│
│  Boards ───── Slack-style shared channels             │
│  Permissions ─ Tool/file/command restrictions         │
│  Communication ─ Text + file references               │
│  Lifecycle ── Message receipt / heartbeat / cron      │
│  Injection ── Role/principles/behavior rules (injected later)│
│                                                       │
└──────────────────────────────────────────────────────┘
        ▲                       │
   Text (incoming)         Text (outgoing)
```

-----

## 3. File Structure

```
animaworks/
├── core/
│   ├── anima.py               # DigitalAnima class
│   ├── agent.py               # AgentCore (execution mode selection, cycle management)
│   ├── anima_factory.py       # Anima creation (template/blank/MD)
│   ├── init.py                # Runtime initialization
│   ├── schemas.py             # Data models (Message, CycleResult, etc.)
│   ├── paths.py               # Path resolution
│   ├── messenger.py           # Inter-Anima message send/receive
│   ├── lifecycle.py           # Heartbeat/cron management (APScheduler)
│   ├── outbound.py            # Outbound message routing
│   ├── schedule_parser.py     # Schedule notation parser
│   ├── logging_config.py      # Log configuration
│   ├── memory/                # Memory subsystem
│   │   ├── manager.py         #   Archive-based memory search/write
│   │   ├── conversation.py    #   Conversation memory (state/conversation.json, rolling compression)
│   │   ├── shortterm.py       #   Short-term memory (chat/heartbeat separated)
│   │   ├── activity.py        #   Unified activity log (JSONL timeline)
│   │   ├── streaming_journal.py #  Streaming journal (WAL)
│   │   ├── priming.py         #   Automatic recall layer (6 channels)
│   │   ├── consolidation.py   #   Memory consolidation (daily/weekly)
│   │   ├── forgetting.py      #   Active forgetting (3 stages)
│   │   ├── task_queue.py      #   Persistent task queue
│   │   ├── resolution_tracker.py # Resolution registry
│   │   └── rag/               #   RAG engine (ChromaDB + sentence-transformers)
│   │       ├── indexer.py, retriever.py, graph.py, store.py
│   │       └── watcher.py     #   File change monitoring
│   ├── supervisor/            # Process supervision
│   │   ├── manager.py         #   ProcessSupervisor (child process launch, monitoring)
│   │   ├── ipc.py             #   Unix Domain Socket IPC
│   │   ├── runner.py          #   Anima process runner
│   │   └── pending_executor.py #   TaskExec (state/pending/ task execution)
│   ├── notification/         # Human notification
│   │   ├── notifier.py        #   HumanNotifier (call_human integration)
│   │   └── channels/         #   Slack, Chatwork, LINE, Telegram, ntfy
│   ├── voice/                 # Voice chat subsystem
│   │   ├── stt.py             #   VoiceSTT (faster-whisper)
│   │   ├── tts_*.py           #   TTS providers (VOICEVOX, ElevenLabs, SBV2)
│   │   └── session.py        #   VoiceSession (STT→Chat IPC→TTS)
│   ├── mcp/                   # MCP server (for Mode S/C)
│   │   └── server.py
│   ├── config/                # Configuration management
│   │   ├── models.py          #   Pydantic unified config model
│   │   ├── cli.py             #   config subcommand
│   │   └── migrate.py         #   Legacy config migration
│   ├── prompt/                # Prompt and context management
│   │   ├── builder.py         #   System prompt construction (6-group structure)
│   │   └── context.py         #   Context window tracking
│   ├── tooling/               # Tool infrastructure
│   │   ├── handler.py         #   Tool execution dispatch, permission checks
│   │   ├── schemas.py         #   Tool schema definitions
│   │   ├── guide.py           #   Dynamic tool guide generation
│   │   └── dispatch.py        #   External tool routing
│   ├── execution/             # Execution engines
│   │   ├── base.py            #   BaseExecutor ABC
│   │   ├── agent_sdk.py       #   Mode S: Claude Agent SDK
│   │   ├── anthropic_fallback.py # Mode A: Anthropic SDK direct
│   │   ├── litellm_loop.py    #   Mode A: LiteLLM + tool_use
│   │   ├── assisted.py        #   Mode B: Framework-assisted
│   │   ├── codex_sdk.py       #   Mode C: Codex CLI wrapper
│   │   └── _session.py        #   Session continuity and chaining
│   └── tools/                 # External tool implementations
│       ├── web_search.py, x_search.py, slack.py
│       ├── chatwork.py, gmail.py, github.py
│       ├── transcribe.py, aws_collector.py
│       ├── image_gen.py       #   Image and 3D model generation
│       └── local_llm.py
├── cli/                       # CLI package
│   ├── parser.py              #   argparse definitions + cli_main()
│   └── commands/              #   Subcommand implementations
├── server/
│   ├── app.py                 # FastAPI application
│   ├── routes/                # API routes (split by domain)
│   │   ├── animas.py, chat.py, sessions.py
│   │   ├── memory_routes.py, logs_routes.py
│   │   ├── channels.py       #   Board/shared channel and DM history API
│   │   ├── voice.py          #   Voice chat WebSocket (/ws/voice/{name})
│   │   ├── system.py, assets.py, config_routes.py
│   │   ├── webhooks.py        #   External messaging webhooks
│   │   └── websocket_route.py
│   ├── websocket.py           # WebSocket management
│   └── static/                # Web UI
│       ├── index.html         # Dashboard
│       ├── modules/           # JS modules (activity, animas, api, app,
│       │                      #   chat, history, login, memory, router,
│       │                      #   state, status, touch, websocket,
│       │                      #   voice, voice-ui, voice-worklet, voice-playback, voice-vad)
│       └── workspace/         # Interactive Workspace
├── templates/
│   ├── prompts/               # Prompt templates
│   ├── anima_templates/       # Anima scaffolding (_blank)
│   ├── roles/                 # Role templates (engineer, researcher, manager, writer, ops, general)
│   ├── common_knowledge/      # Shared knowledge templates
│   ├── common_skills/         # Common skill templates
│   └── company/               # Organization vision templates
├── main.py                    # CLI entry point
└── tests/                     # Test suite
```

### 3.1 Anima Directory (`~/.animaworks/animas/{name}/`)

Each Anima is composed of the following files and directories:

|File / Directory            |Description                         |
|----------------------------|------------------------------------|
|`identity.md`               |Personality and strengths (immutable baseline)|
|`injection.md`              |Role, principles, behavior rules (replaceable)|
|`permissions.md`            |Tool/file/command permissions        |
|`heartbeat.md`              |Periodic check interval and active hours|
|`cron.md`                   |Scheduled tasks (YAML)              |
|`bootstrap.md`              |Self-construction instructions on first launch|
|`status.json`               |Enabled/disabled, role, model settings|
|`specialty_prompt.md`       |Role-specific specialized prompt     |
|`assets/`                   |Character images and 3D models       |
|`transcripts/`              |Conversation transcripts             |
|`skills/`                   |Personal skills (YAML frontmatter + Markdown body)|
|`activity_log/`             |Unified activity log (daily JSONL)   |
|`state/`                    |Working memory (current_task.md, pending.md, pending/, task_queue.jsonl)|
|`episodes/`                 |Episodic memory (daily logs)         |
|`knowledge/`                |Semantic memory (learned knowledge)  |
|`procedures/`               |Procedural memory (runbooks)         |
|`shortterm/`                |Short-term memory (chat/ and heartbeat/ separated, session continuity)|

### 3.2 config.json (Unified Configuration)

All settings are consolidated in `~/.animaworks/config.json`. Validated with the Pydantic `AnimaWorksConfig` model, with support for per-person overrides.

**Top-Level Structure:**

|Section                |Description                          |
|-----------------------|-------------------------------------|
|`system`               |Operation mode, log level            |
|`credentials`           |Per-provider API keys and endpoints (named map)|
|`model_modes`          |※Deprecated. Replaced by `~/.animaworks/models.json`. Referenced as fallback|
|`model_context_windows`|Model name pattern → context window size override (fnmatch)|
|`anima_defaults`       |Default values applied to all Animas |
|`animas`               |Organization layout (supervisor, speciality) only. Model settings use status.json as SSoT|
|`consolidation`        |Memory consolidation settings (daily/weekly execution times and thresholds)|
|`rag`                  |RAG settings (embedding model, graph spreading activation, etc.)|
|`priming`              |Automatic recall settings (per-message-type token budgets)|
|`image_gen`            |Image generation settings (style consistency, Vibe Transfer)|
|`human_notification`   |Human notification settings (channels: Slack/LINE/Telegram/Chatwork/ntfy)|
|`server`               |Server runtime settings (IPC, keep-alive, streaming)|
|`external_messaging`   |External messaging integration (Slack Socket Mode, Chatwork Webhook)|
|`background_task`      |Background tool execution settings (target tools, thresholds)|
|`activity_log`         |Log rotation settings (rotation_mode, max_size_mb, max_age_days)|
|`heartbeat`            |Heartbeat schedule and cascade prevention settings|
|`voice`                |Voice chat settings (STT/TTS providers)|
|`housekeeping`         |Periodic disk cleanup settings|

**Configuration Resolution (2-Layer Merge — status.json SSoT):**

Model settings at Anima startup are resolved in two layers with `status.json` as the Single Source of Truth (SSoT):

1. **Layer 1: status.json** (highest priority) — Model and execution parameters in `animas/{name}/status.json`
2. **Layer 2: config.json anima_defaults** (fallback) — Global defaults in `config.anima_defaults`

The `animas` section in `config.json` holds only the organization layout (`supervisor`, `speciality`).

**AnimaModelConfig Fields (config.json animas):**

|Field         |Type            |Description                        |
|--------------|----------------|-----------------------------------|
|`supervisor`  |`str \| null`   |Name of the supervisory Anima      |
|`speciality`  |`str \| null`   |Free-text area of expertise        |
|`model`       |`str \| null`   |Override (status.json takes priority)|

**status.json Model-Related Fields (SSoT):**

|Field                                |Type            |Default                   |Description                        |
|-------------------------------------|----------------|--------------------------|-----------------------------------|
|`model`                              |`str`           |`claude-sonnet-4-6`       |Model name to use (provider prefix allowed)|
|`fallback_model`                     |`str \| null`   |`null`                    |Fallback model                     |
|`max_tokens`                         |`int`           |`8192`                    |Maximum tokens per response        |
|`max_turns`                          |`int`           |`20`                      |Maximum turns per cycle            |
|`credential`                         |`str`           |`"anthropic"`             |Credential name to use             |
|`context_threshold`                  |`float`         |`0.50`                    |Threshold for short-term memory externalization (context usage ratio)|
|`max_chains`                         |`int`           |`2`                       |Maximum automatic session continuations|
|`conversation_history_threshold`     |`float`         |`0.30`                    |Compression trigger for conversation memory (context usage ratio)|
|`execution_mode`                     |`str \| null`   |`null` (auto-detect)      |`"S"` / `"A"` / `"B"` / `"C"`. Resolved via models.json or DEFAULT_MODEL_MODE_PATTERNS when unset|
|`supervisor`                         |`str \| null`   |`null`                    |Name of the supervisory Anima      |
|`speciality`                         |`str \| null`   |`null`                    |Free-text area of expertise        |

**config.json Example:**

```json
{
  "version": 1,
  "system": { "mode": "server", "log_level": "INFO" },
  "credentials": {
    "anthropic": { "api_key": "", "base_url": null },
    "ollama": { "api_key": "dummy", "base_url": "http://localhost:11434/v1" }
  },
  "anima_defaults": {
    "model": "claude-sonnet-4-6",
    "max_tokens": 4096,
    "max_turns": 20,
    "credential": "anthropic",
    "context_threshold": 0.50,
    "conversation_history_threshold": 0.30
  },
  "animas": {
    "alice": {},
    "bob": { "model": "gpt-4o", "credential": "openai", "supervisor": "alice" }
  }
}
```

**Security:** config.json is saved with `0o600` permissions (owner read/write only). API key management via environment variables is also supported.

**Context Window Resolution** (`resolve_context_window()` in `core/prompt/context.py`):

1. config.json `model_context_windows` (highest priority — fnmatch wildcard patterns)
2. `MODEL_CONTEXT_WINDOWS` hardcoded dict (fallback — prefix match)
3. `_DEFAULT_CONTEXT_WINDOW` = 128,000 (final fallback)

Hardcoded defaults use conservative values (e.g. `claude-sonnet-4-6: 128,000`). Override via config when a larger window is needed. The compaction threshold is auto-scaled: models with >= 200K windows use the configured value (default 0.50); smaller models scale linearly toward 0.98.

### 3.3 Model and Authentication Settings (credentials)

#### Per-Provider credentials Configuration

Define per-provider authentication in the `credentials` section of `config.json` as a named map. Anima's `status.json` references these by key name.

```json
{
  "credentials": {
    "anthropic": {
      "type": "api_key",
      "api_key": "sk-ant-api03-xxxxx",
      "keys": {},
      "base_url": null
    },
    "bedrock": {
      "type": "api_key",
      "api_key": "",
      "keys": {
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "...",
        "aws_region_name": "ap-northeast-1"
      },
      "base_url": null
    },
    "azure": {
      "type": "api_key",
      "api_key": "BKQ5t...",
      "keys": { "api_version": "2025-01-01-preview" },
      "base_url": "https://your-resource.openai.azure.com"
    },
    "vertex": {
      "type": "api_key",
      "api_key": "",
      "keys": {
        "vertex_project": "my-gcp-project",
        "vertex_location": "asia-northeast1",
        "vertex_credentials": "/path/to/service-account.json"
      },
      "base_url": null
    },
    "vllm-gpu": {
      "api_key": "dummy",
      "base_url": "http://localhost:8000/v1"
    }
  }
}
```

vLLM provides an OpenAI-compatible API, so connect with the `openai/` prefix. A dummy `api_key` is required even when authentication is disabled. Anima config: `model: "openai/glm-4.7-flash"`, `credential: "vllm-gpu"`.

#### Model Naming Conventions

Model names include the provider prefix (following LiteLLM naming conventions):

| Provider | Format | Example |
|----------|--------|---------|
| Anthropic direct | `claude-{tier}-{version}` | `claude-opus-4-6`, `claude-sonnet-4-6` |
| AWS Bedrock | `bedrock/{region}.anthropic.claude-{tier}-{version}` | `bedrock/jp.anthropic.claude-sonnet-4-6` |
| Azure OpenAI | `azure/{deployment-name}` | `azure/gpt-4.1-mini` |
| Google Vertex AI | `vertex_ai/{model-name}` | `vertex_ai/gemini-2.5-flash` |
| OpenAI direct | `openai/{model-name}` | `openai/gpt-4.1` |
| Codex | `codex/{model-name}` | `codex/gpt-5.3-codex` |
| Ollama | `ollama/{model-name}` | `ollama/qwen3:8b` |
| vLLM (local) | `openai/{model-name}` + credential base_url | `openai/glm-4.7-flash` |

#### status.json Model-Related Fields

| Field | Required | Description |
|-------|----------|-------------|
| `model` | Yes | Model name (with prefix above) |
| `credential` | Yes | Key name in config.json `credentials` |
| `execution_mode` | No | Execution mode. Auto-resolved via `DEFAULT_MODEL_MODE_PATTERNS` when unset |
| `mode_s_auth` | No | Authentication method for Mode S (Agent SDK) (`"api"` / `"bedrock"` / `"vertex"`) |

#### execution_mode Auto-Resolution

When `execution_mode` is not set in `status.json`, `resolve_execution_mode()` resolves it in this order:

1. Per-anima explicit override (status.json `execution_mode`)
2. `models.json` (`~/.animaworks/models.json`, user-editable)
3. config.json `model_modes` (deprecated fallback)
4. `DEFAULT_MODEL_MODE_PATTERNS` (code defaults)
5. Default `"B"` (safe fallback)

**Main DEFAULT_MODEL_MODE_PATTERNS mappings:**

| Pattern | Mode | Description |
|---------|------|-------------|
| `claude-*` | S | Claude direct → Agent SDK |
| `codex/*` | C | Codex → CLI wrapper |
| `openai/*`, `azure/*`, `bedrock/*`, `vertex_ai/*`, `google/*`, etc. | A | Cloud API → LiteLLM + tool_use |
| `ollama/qwen3.5*`, `ollama/glm-4.7*`, etc. | A | tool_use-capable Ollama |
| `ollama/*` | B | Other Ollama → Basic (one-shot assisted) |

**Note:** `bedrock/*` defaults to Mode A. For Mode S, explicitly set both `"execution_mode": "S"` and `"mode_s_auth": "bedrock"`.

#### Configuration Pattern Examples

**Claude Opus (Anthropic Max Plan):**
```json
{ "model": "claude-opus-4-6", "credential": "anthropic" }
```

**Claude Sonnet (via AWS Bedrock + Mode S):**
```json
{
  "model": "bedrock/jp.anthropic.claude-sonnet-4-6",
  "credential": "bedrock",
  "execution_mode": "S",
  "mode_s_auth": "bedrock"
}
```

**Azure OpenAI:**
```json
{ "model": "azure/gpt-4.1-mini", "credential": "azure" }
```

**RAGConfig Fields:**

|Field                          |Type      |Default                           |Description                        |
|-------------------------------|----------|----------------------------------|-----------------------------------|
|`enabled`                      |`bool`    |`true`                            |Enable/disable RAG functionality   |
|`embedding_model`              |`str`     |`intfloat/multilingual-e5-small`  |Embedding model to use             |
|`use_gpu`                      |`bool`    |`false`                           |Whether to use GPU                 |
|`enable_spreading_activation`  |`bool`    |`true`                            |Enable/disable graph-based spreading activation|
|`max_graph_hops`               |`int`     |`2`                               |Maximum hops for graph traversal   |
|`enable_file_watcher`          |`bool`    |`true`                            |Enable/disable file change monitoring|
|`graph_cache_enabled`          |`bool`    |`true`                            |Enable/disable graph cache         |
|`implicit_link_threshold`      |`float`   |`0.75`                            |Similarity threshold for implicit link generation|
|`spreading_memory_types`       |`list`    |`["knowledge", "episodes"]`        |Memory types targeted by spreading activation|

**PrimingConfig Fields:**

|Field                 |Type    |Default |Description                        |
|----------------------|--------|--------|-----------------------------------|
|`dynamic_budget`      |`bool`  |`true`  |Enable/disable dynamic budget allocation|
|`budget_greeting`     |`int`   |`500`   |Token budget for greeting messages |
|`budget_question`     |`int`   |`1500`  |Token budget for question messages |
|`budget_request`      |`int`   |`3000`  |Token budget for request messages  |
|`budget_heartbeat`    |`int`   |`200`   |Token budget for heartbeat (fallback)|
|`heartbeat_context_pct`|`float`|`0.05`  |HB context ratio when dynamic budget (5%)|

**ServerConfig Fields:**

|Field                          |Type     |Default |Description                        |
|-------------------------------|---------|--------|-----------------------------------|
|`ipc_stream_timeout`           |`int`    |`60`    |IPC streaming per-chunk timeout (seconds)|
|`keepalive_interval`           |`int`    |`30`    |Keep-alive send interval (seconds) |
|`max_streaming_duration`       |`int`    |`1800`  |Maximum streaming duration (seconds)|
|`stream_checkpoint_enabled`    |`bool`   |`true`  |Save tool results during streaming |
|`stream_retry_max`             |`int`    |`3`     |Maximum auto-retry count on stream disconnection|
|`stream_retry_delay_s`         |`float`  |`5.0`   |Wait time between retries (seconds)|

**ExternalMessagingConfig Fields:**

|Field                 |Type          |Default    |Description                        |
|----------------------|--------------|-----------|-----------------------------------|
|`preferred_channel`   |`str`         |`"slack"`  |Preferred send channel (`"slack"` or `"chatwork"`)|
|`user_aliases`        |`dict`        |`{}`       |User alias to contact info mapping |
|`slack`               |`object`      |           |Slack settings (enabled, mode, anima_mapping)|
|`chatwork`            |`object`      |           |Chatwork settings (enabled, mode, anima_mapping)|

**BackgroundTaskConfig Fields:**

|Field                     |Type    |Default |Description                        |
|--------------------------|--------|--------|-----------------------------------|
|`enabled`                 |`bool`  |`true`  |Enable/disable background execution|
|`eligible_tools`          |`dict`  |        |Map of target tool names to thresholds (threshold_s)|
|`result_retention_hours`  |`int`   |`24`    |Result retention period (hours)    |

-----

## 4. Memory System (Archive-Based)

### 4.1 Design Philosophy

Traditional AI agents mechanically truncate memory and pack it into prompts (truncation-based). This is equivalent to "anterograde amnesia where only the most recent memories exist."

The archive-based approach is different. Just as a person retrieves the documents they need from an archive, **Digital Anima searches for and retrieves only the memories it needs, when it needs them.** There is no upper limit on memory capacity. Only "what is needed right now" enters the context.

### 4.2 Correspondence with Neuroscience Models

```
┌─────────────────────────────────────────────────┐
│  Working Memory (Prefrontal Cortex)             │
│  = Context Window                               │
│  Limited capacity. Temporary holding of          │
│  "what I'm currently thinking about"             │
│  → Delegated to the SDK. No additional           │
│    implementation needed                         │
└──────────────────┬──────────────────────────────┘
                    │ Recall (search) / Encoding (write)
┌──────────────────┴──────────────────────────────┐
│  Long-Term Memory (Cerebral Cortex /             │
│  Hippocampal System)                             │
│                                                    │
│  episodes/   Episodic memory — what happened     │
│              and when                             │
│  knowledge/  Semantic memory — lessons and        │
│              knowledge learned                    │
│  procedures/ Procedural memory — work runbooks    │
└────────────────────────────────────────────────┘
```

### 4.3 Role of Memory Directories

|Directory                     |Brain Analog              |Contents              |Update Method                |
|------------------------------|--------------------------|----------------------|-----------------------------|
|`state/`                      |Persistent part of working memory|Current state, incomplete tasks|Overwritten each cycle       |
|`state/conversation.json`     |Conversation memory       |Rolling conversation history|LLM summarization when threshold exceeded|
|`shortterm/chat/`            |Short-term memory (chat)  |Context carry-over    |Auto-externalized on session switch|
|`shortterm/heartbeat/`       |Short-term memory (heartbeat)|Context carry-over    |Separate from chat/heartbeat |
|`episodes/`                   |Episodic memory (hippocampus)|Daily action logs     |Appended to date-based files |
|`knowledge/`                  |Semantic memory (temporal cortex)|Lessons, rules, counterpart traits|Created/updated by topic     |
|`procedures/`                 |Procedural memory (basal ganglia)|Work runbooks         |Revised as needed            |

### 4.4 Memory Operations

**Recall (remembering)** — Always search the archive before making decisions.

1. Search `knowledge/` by keywords (counterpart name, topic, etc.)
1. Search `episodes/` as needed (what happened in the past)
1. Check `procedures/` if the procedure is unclear
1. Load relevant memories before making a decision

**Encoding (writing)** — Update memories after taking action.

1. Append an action log to `episodes/YYYY-MM-DD.md`
1. Write to `knowledge/` if something new was learned
1. Protect important lessons with the `[IMPORTANT]` tag
1. Update `state/current_task.md`

**Consolidation (reflection)** — Transfer from episodic to semantic memory. Corresponds to memory consolidation during sleep in neuroscience.

- Extract patterns from `episodes/` logs and generalize them into `knowledge/`
- Run periodically via heartbeat or cron

### 4.5 Episodic Memory Format

```markdown
# 2026-02-12 Action Log

## 09:15 Chatwork Unreplied Check
- Trigger: Heartbeat
- Decision: Found 2 unreplied messages. Handle internal ones myself, escalate external ones
- Result: Drafted replies and obtained approval
- Lesson: None

## 14:30 Reply to Tanaka-san
- Trigger: Message received
- Decision: Recalled previous rejection for casual tone → drafted formal version
- Result: Approved
- Lesson: Reconfirmed that the approach for the construction industry is correct
```

### 4.6 Knowledge Format

```markdown
# Response Guidelines

## Communication Rules
- [IMPORTANT] Always respond with formal business language
- Casual tone is not acceptable (rejected on 2026-02-11)
- The construction industry values formal communication

## Contacts
- Primary contact: Tanaka-san
```

### 4.7 Experimental Validation Results

Archive-based memory achieved S-rank on all 5 criteria in manual testing (conducted 2026-02-12).

- **Recall**: Successfully searched for and utilized past memories not present in the prompt
- **Encoding**: Properly wrote action logs, lessons, and new knowledge to files
- **Reflexion**: Extracted lessons from rejection (failure) and changed subsequent decisions
- **Consolidation**: Extracted meta-patterns from individual episodes and generalized them as knowledge
- **Restoration**: Restored state from `state/` and `episodes/` after context was cleared

The key to success was a strong system prompt instruction: "Making decisions without searching memory is prohibited."

### 4.8 Conversation Memory (ConversationMemory)

Rolling chat history. When the accumulated size exceeds `conversation_history_threshold` (default 30%), older turns are compressed via LLM summarization while recent turns retain their original text. Saved in `{anima_dir}/state/conversation.json`.

### 4.9 Short-Term Memory (ShortTermMemory)

Externalized memory for session continuity. When the context threshold is exceeded in A mode, `session_state.json` (machine-readable) and `session_state.md` (for next prompt injection) are generated. `shortterm/{chat|heartbeat}/` separates chat and heartbeat; auto-archived to `archive/`.

### 4.10 Unified Activity Log (ActivityLogger)

An append-only JSONL log that records all interactions as a single timeline.

- **File location**: `{anima_dir}/activity_log/{date}.jsonl`
- **Event types**: `message_received`, `message_sent`, `response_sent`, `channel_read`, `channel_post`, `human_notify`, `tool_use`, `heartbeat_start`, `heartbeat_end`, `cron_executed`, `memory_write`, `error` (`dm_sent` is a backward-compatible alias for `message_sent`, `dm_received` for `message_received`)
- **Entry fields**: `ts` (ISO 8601), `type`, `content`, `summary`, `from`/`to`, `channel`, `tool`, `via`, `meta`
- **Priming integration**: Injects recent activity into the system prompt, enabling cross-session context continuity
- **Purpose**: The single data source for the Priming layer's "recent activity" channel. Unifies previously scattered transcript, dm_log, and heartbeat_history files

### 4.11 Streaming Journal (StreamingJournal)

A crash-resilient Write-Ahead Log (WAL). Incrementally persists streaming output to disk.

- **File location**: `{anima_dir}/shortterm/streaming_journal_{session_type}.jsonl` (separated by `chat` / `heartbeat`)
- **Lifecycle**: `open()` → `write_text()` / `write_tool_*()` → `finalize()` (file deleted on normal completion)
- **Crash recovery**: On next startup, `recover()` reads orphaned journals and restores them as `JournalRecovery`
- **Buffering**: Flushed at 1-second intervals or 500 characters, with persistence guaranteed via fsync
- **Event types**: `start` (trigger and session info), `text` (text chunks), `tool_start` / `tool_end`, `done`

### 4.12 Priming (Automatic Recall)

Injects 6-channel parallel automatic memory search into the system prompt. `PrimingEngine` acts as the sole activity leader (hippocampal model) for prompt construction.

| Channel | Budget | Source |
|---------|--------|--------|
| A: sender_profile | 500 tokens | Direct read of shared/users/{sender}/index.md |
| B: recent_activity | 1300 tokens | Unified timeline from ActivityLogger |
| C: related_knowledge | 700–1200 tokens | Dense vector search (RAG) |
| D: skill_match | 200 tokens | Description-based 3-stage matching (skill names only, max 5) |
| E: pending_tasks | 300 tokens | TaskQueueManager (persistent task queue summary) |
| F: episodes | 400–500 tokens | Dense vector search (RAG, episodes/) |

Channel D returns only the **names** of matched skills/procedures. Full text is not injected (progressive disclosure: agent loads details via `skill` tool when needed).

### 4.13 RAG Configuration

The embedding model is selectable via `rag.embedding_model` in `config.json`. Default is `intfloat/multilingual-e5-small` (384 dimensions). GPU usage and graph-based spreading activation are also configured in config.json.

-----

## 5. Identity (Self-Definition)

The information that allows a Digital Anima to recognize "who it is." Always resident in working memory.

```markdown
# Identity: Tanaka

## Personality Traits
- Cautious, considers risks first
- Detail-oriented, dislikes ambiguity

## Perspective
Prioritizes technical feasibility. "Will it actually work?" is always the starting point for decisions.

## Strengths
- Backend design, performance optimization

## Weaknesses
- UI/UX design decisions, understanding users' emotional needs
```

-----

## 6. Permissions

Restrictions on "what a Digital Anima can do." Permission restrictions create "limited visibility," which produces dependence on others — and that dependence is what makes the organization valuable.

```markdown
# Permissions: Tanaka

## Available Tools
Read, Write, Edit, Bash, Grep, Glob

## Unavailable Tools
WebSearch, WebFetch

## Readable Locations
- Under /project/src/backend/
- Under /project/docs/
- Under /shared/reports/

## Writable Locations
- Under /project/src/backend/
- Under /workspace/Tanaka/

## Invisible Locations
- /project/.env
- Under /project/src/frontend/ (Suzuki's jurisdiction)

## Allowed Commands
npm test, npm run build, git diff, git log

## Disallowed Commands
git push (requires approval), rm -rf, docker
```

Since the frontend code is unreadable, the agent needs to ask a colleague, "What are the frontend constraints?" This "asking because I don't know" is what drives horizontal communication in the organization.

-----

## 7. Communication

### Principles

- Text and file references only. Direct sharing of internal state is prohibited
- Compress and interpret information in your own words before communicating. Never send the full context
- For lengthy content, save it as a file and communicate: "I've placed it here, please take a look"

### Message Structure

```json
{
  "id": "20260213_100000_abc",
  "thread_id": "",
  "reply_to": "",
  "from_person": "Tanaka",
  "to_person": "Suzuki",
  "type": "message",
  "content": "I've revised the auth API design. I placed it in auth-api-design.md, please review.",
  "attachments": [],
  "timestamp": "2026-02-13T10:00:00Z"
}
```

### Message Types

In the current implementation, the `type` field defaults to the single type `"message"`. The following type classifications are retained in the design for future extension.

|type (future extension) |Description          |
|------------------------|---------------------|
|request                 |Request or instruction from a superior|
|report                  |Report to a superior |
|consultation            |Consultation with a peer|
|broadcast               |Organization-wide announcement|

Suzuki sees only the design document. Tanaka's thought process and discarded alternatives are invisible. This information asymmetry is what enables fresh perspectives from different backgrounds.

-----

## 8. Lifecycle

### 8.1 Activation Triggers and Execution Paths

A Digital Anima has its own internal clock. The four execution paths hold independent locks and can run in parallel.

|Path         |Lock |Trigger |Role |
|-------------|-----|--------|-----|
|**Chat/Inbox** | `_conversation_lock` / `_inbox_lock` | Human chat / Anima DM | Message response. Inbox: immediate, lightweight replies only |
|**Heartbeat** | `_background_lock` | Periodic check (30 min) | Observe → Plan → Reflect. Does not execute |
|**Cron** | `_background_lock` | cron.md schedule | Same context as Heartbeat; scheduled task execution |
|**TaskExec** | `_background_lock` | Task appears in state/pending/ | Delegated task execution (minimal context) |

Heartbeat only observes and plans; tasks to execute are written to `state/pending/` in JSON format. TaskExec detects them via 3-second polling and runs them in a separate LLM session.

### 8.2 Heartbeat

The act of periodically "looking up and scanning the surroundings" at regular intervals. Executes while retaining the main context; does nothing if there is nothing to address.

```markdown
# Heartbeat: Tanaka

## Execution Interval
Every 30 minutes

## Active Hours
9:00 - 22:00 (JST)

## Checklist
- Are there unread messages in the inbox?
- Has a blocker arisen for any in-progress task?
- Have new files been placed in my work area?
- If nothing, do nothing (HEARTBEAT_OK)

## Notification Rules
- Notify relevant parties only when deemed urgent
- Do not repeat the same notification within 24 hours
```

### 8.3 cron

Performs predetermined tasks at predetermined times on its own clock. Unlike heartbeat, it always executes something and produces a result.

cron does not depend on external schedulers or organizational structure. **Each Digital Anima owns its own cron.** Just as a person has their own habit of writing a diary every morning.

```markdown
# Cron: Tanaka

## Morning Work Planning (Daily 9:00 JST)
Review yesterday's progress from long-term memory and plan today's tasks.
Prioritize based on principles and objectives.
Output the result to /workspace/Tanaka/daily-plan.md.

## Weekly Retrospective (Every Friday 17:00 JST)
Re-read this week's episodes/ and extract patterns, consolidating them into knowledge/.
(Memory consolidation = the neuroscience analog of memory fixation during sleep)
```

**Differences Between Heartbeat and cron:**

|Aspect      |Heartbeat              |cron                   |
|------------|-----------------------|-----------------------|
|Human analog|Occasionally checking email while working|Morning routine, weekly retrospective|
|Context     |Retained               |Not retained (new session)|
|Decision    |"Is there anything I should care about?"|Executed unconditionally|
|When idle   |Does nothing           |Always produces output |
|Ownership   |Internal to the individual|Internal to the individual|

### 8.4 Flow of a Single Cycle

```
Activation (message or heartbeat or cron)
  ↓
Recall: Search the archive for relevant memories
  ↓
Think & Act: Agent Core (S/A/B mode) processes
  ↓
Communicate: Summarize results and send as text or create files
  ↓
Encode: Write action logs, lessons, and knowledge
  ↓
Update state: Update state/
  ↓
Rest
```

-----

## 9. Injectable Slot (Post-Injection)

Digital Anima is an "empty vessel." Roles and principles are injected via Markdown.

```markdown
# Injection: Tanaka

## Role
Tech Lead. Responsible for technical decision-making and code review.
Area of responsibility: backend architecture.

## Principles
Solve user problems through high-quality software.

## Code of Conduct
- Never compromise on quality
- Pursue simplicity
- When in doubt, return to "What is best for the user?"

## Things Not To Do
- Direct access to the production database
- Frontend implementation (delegate to Suzuki)
- Pushing to the main branch without approval
```

-----

## 10. System Prompt Construction

The various Markdown files and templates are combined to build a single system prompt. `build_system_prompt()` in `core/prompt/builder.py` assembles a 6-group structure. The `trigger` parameter (`chat` / `inbox` / `heartbeat` / `cron` / `task`) selects sections according to the execution path.

```
Group 1: Operating environment and behavior rules
  - environment.md (guardrails, folder structure)
  - Current time (JST)
  - behavior_rules (search before deciding)
  - tool_data_interpretation.md (trust level interpretation for tool results and Priming)

Group 2: Who you are
  - bootstrap.md (first-launch instructions — conditional)
  - company/vision.md (organization vision)
  - identity.md (personality)
  - injection.md (role, principles)
  - specialty_prompt.md (role-specific specialized prompt)
  - permissions.md (tool and command permissions)

Group 3: Current situation
  - state/current_task.md + pending.md (in-progress tasks)
  - Task Queue (persistent task queue — conditional)
  - Resolution Registry (resolved issues, last 7 days — conditional)
  - Recent Outbound (send history, last 2 hours, max 3 — conditional)
  - Priming (RAG automatic recall — conditional)
  - Recent Tool Results (conditional)

Group 4: Memory and capabilities
  - memory_guide (memory directory guide)
  - common_knowledge hint (shared reference hints — conditional)
  - Hiring rules (when newstaff skill present — conditional)
  - Tool guide (S/A/B/C mode-specific)
  - External tool guide (when permitted — conditional)

Group 5: Organization and communication
  - hiring context (when solo top-level — conditional)
  - org context (organization structure tree)
  - messaging instructions (messaging instructions)
  - human notification guidance (top-level & when notifications enabled — conditional)

Group 6: Meta settings
  - emotion metadata (facial expression metadata instructions)
  - A reflection (self-correction prompt for A mode — conditional)
```

**Tiered System Prompt:** Adjusts prompt content in 4 tiers based on context window (T1 FULL 128k+ / T2 STANDARD 32k–128k / T3 LIGHT 16k–32k / T4 MINIMAL <16k).

**Skill injection (progressive disclosure):** Channel D returns only the **names** of matched skills/procedures. Full text is loaded on demand via the `skill` tool. Budget is determined by message type: greeting=500, question=1500, request=3000, heartbeat=200.

Including "Making decisions without searching memory is prohibited" in `behavior_rules` is the key to the success of archive-based memory (validated experimentally).

-----

## 11. Implemented Features

- **Digital Anima class** — Encapsulation and autonomous operation. 1 Anima = 1 directory
- **4 execution modes** — S: Claude Agent SDK / A: Anthropic SDK or LiteLLM + tool_use / B: Assisted (one-shot) / C: Codex CLI wrapper
- **ProcessSupervisor** — Launches and monitors each Anima as an independent child process with Unix socket
- **Archive-based memory** — episodes (daily logs) / knowledge (lessons and knowledge) / procedures (runbooks) / state (working memory)
- **Conversation memory** — state/conversation.json, rolling compression. Older turns compressed via LLM summarization when threshold exceeded
- **Short-term memory** — shortterm/chat/ and heartbeat/ separated. Externalized as JSON+MD when context threshold exceeded
- **Unified activity log** — All interactions recorded in activity_log/ as JSONL timeline. Priming integration for context continuity
- **Streaming journal (WAL)** — streaming_journal_{session_type}.jsonl. Crash-resilient incremental persistence
- **Priming (6 channels)** — sender_profile, recent_activity, related_knowledge, skill_match, pending_tasks, episodes
- **Board/shared channels** — Slack-style shared channels. REST API for channel posts, mentions, DM history
- **Unified outbound routing** — Auto-resolves recipient names to internal Anima or external platforms (Slack/Chatwork) for delivery
- **Heartbeat, cron, TaskExec** — Schedule management via APScheduler. Tasks in state/pending/ executed by TaskExec via 3-second polling
- **Inter-Anima messaging** — Text communication via Messenger. Hierarchical delegation (supervisor → subordinate, delegate_task tool)
- **Supervisor tools** — Auto-enabled for Animas with subordinates: disable/enable_subordinate, delegate_task, org_dashboard, audit_subordinate, etc.
- **Unified configuration** — config.json + Pydantic validation. status.json SSoT, models.json for execution mode override
- **FastAPI server** — REST + WebSocket + Web UI (3D office, conversation view)
- **Voice chat** — WebSocket /ws/voice/{name}. STT (faster-whisper) → Chat IPC → TTS (VOICEVOX/ElevenLabs/SBV2)
- **External tools** — web_search, x_search, slack, chatwork, gmail, github, transcribe, aws_collector, local_llm, image_gen, google_calendar, call_human
- **Anima creation** — From template / blank (_blank) / MD file (create --from-md)
- **Skill progressive disclosure** — Only matched skill names injected. Full text loaded on demand via `skill` tool
- **External messaging integration** — Slack Socket Mode (real-time bidirectional), Chatwork Webhook (inbound)
- **Embedding model configuration** — RAG embedding model selectable via config.json
- **Persistent task queue** — task_queue.jsonl. Staleness detection and delegation prompt injection
- **Resolution registry** — Cross-Anima issue resolution tracking via shared/resolutions.jsonl
- **Human notification** — call_human integration. Slack, Chatwork, LINE, Telegram, ntfy channels

-----

## 12. Design Decision Log

|Decision                               |Rationale                                                           |
|---------------------------------------|--------------------------------------------------------------------|
|Memory format: JSON → Markdown files   |Experiments showed that AI reads and writes Markdown more naturally, with better Grep search compatibility|
|Forgetting: score-based → [IMPORTANT] tag + consolidation|Simple tag-based approach is more practical. Consolidation naturally organizes importance|
|config.md → config.json                |From per-anima MD to unified JSON. Pydantic validation + per-anima overrides|
|Do not build the agent loop ourselves  |Delegate to the Claude Agent SDK. No reinventing the wheel         |
|4-way execution mode branching (S/A/B/C)|Claude SDK first priority, Anthropic SDK fallback, LiteLLM for general use, Assisted for weak models, Codex CLI wrapper. All within the Anima capsule|
|agent.py refactoring                   |Split into execution/, tooling/, memory/. ProcessSupervisor for child process launch|
|Permissions as "limited visibility"   |Not knowing things forces asking others. Omniscience makes organizations meaningless|
|Archive-based memory adopted           |Truncation-based (packing the last N entries into the prompt) does not scale memory. Archive-based has no upper limit on memory capacity|
|cron as the "individual's" internal clock|cron is not an organizational scheduler; each Digital Anima owns its own habits. Just as a person has their own daily routine|
