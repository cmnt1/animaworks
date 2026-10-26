<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/modules.md -->
<!-- i18n: source-sha256=7a7fd10c38325936902a7ce867a67bfc2eba571ed2e65ac728e48c63bb7a4edd generated=2026-10-26 engine=manual model=codex translator=2 -->

# Module List

The Python files tracked in `git ls-files core cli server` are listed here. Private modules are marked.

## `cli`

—

| Module | Lines | docstring 1st line |
|---|---:|---|
| `cli` | 9 | — |
| `cli.__main__（非公開）` | 9 | — |
| `cli._anima_tool（非公開）` | 33 | — |
| `cli._gateway（非公開）` | 93 | — |
| `cli.codex_command_hook` | 64 | CLI adapter for Codex's ``PreToolUse`` command-policy hook. |
| `cli.demo` | 407 | Native ``animaworks demo`` command. |
| `cli.parser` | 873 | — |
| `cli.tool_dispatch` | 414 | CLI dispatch for external tools, submit tasks, and command aliases. |

## `cli.commands`

—

| Module | Lines | docstring 1st line |
|---|---:|---|
| `cli.commands` | 5 | — |
| `cli.commands.anima` | 303 | — |
| `cli.commands.anima_mgmt` | 1205 | CLI commands for anima process management. |
| `cli.commands.anima_urgent` | 124 | CLI commands for urgent-mode task submission. |
| `cli.commands.board` | 144 | — |
| `cli.commands.company_cmd` | 272 | — |
| `cli.commands.config_cmd` | 238 | CLI handlers and interactive wizard for ``animaworks config``. |
| `cli.commands.cost_cmd` | 326 | — |
| `cli.commands.enclave_cmd` | 327 | Operational commands for enclave runtimes. |
| `cli.commands.import_cmd` | 88 | — |
| `cli.commands.index_cmd` | 380 | — |
| `cli.commands.init_cmd` | 155 | — |
| `cli.commands.internal_cmd` | 156 | — |
| `cli.commands.logs` | 212 | CLI commands for viewing anima logs. |
| `cli.commands.mcp_cmd` | 66 | — |
| `cli.commands.memory_cmd` | 56 | — |
| `cli.commands.messaging` | 86 | — |
| `cli.commands.migrate_cmd` | 114 | — |
| `cli.commands.models_cmd` | 303 | CLI commands for model information and management. |
| `cli.commands.optimize_assets` | 189 | — |
| `cli.commands.profile` | 327 | — |
| `cli.commands.rag_repair_status` | 147 | Status reporting for persistent RAG repair state. |
| `cli.commands.remake_cmd` | 272 | — |
| `cli.commands.repair_rag_cmd` | 135 | — |
| `cli.commands.server` | 902 | — |
| `cli.commands.skills` | 211 | — |
| `cli.commands.supervisor_cmd` | 91 | — |
| `cli.commands.task_cmd` | 667 | — |
| `cli.commands.task_store_cmd` | 258 | Operator-only, cohort-scoped task migration and current-state export. |
| `cli.commands.tmp_cmd` | 173 | — |
| `cli.commands.vault_cmd` | 309 | — |

## `cli.tui`

—

| Module | Lines | docstring 1st line |
|---|---:|---|
| `cli.tui` | 207 | — |
| `cli.tui.app` | 1936 | — |
| `cli.tui.client` | 394 | — |
| `cli.tui.commands` | 251 | — |
| `cli.tui.keybindings` | 90 | Keybinding configuration for the TUI. |
| `cli.tui.markdown` | 535 | Markdown → Rich renderables, tuned for a terminal transcript. |
| `cli.tui.session` | 246 | Session persistence for the TUI. |
| `cli.tui.sse` | 98 | — |
| `cli.tui.state` | 280 | Pure client-side UI state for the TUI sidebar, activity feed and palette. |
| `cli.tui.widgets.call_human` | 85 | A call_human notification card rendered in the transcript. |
| `cli.tui.widgets.chat_input` | 152 | — |
| `cli.tui.widgets.palette` | 115 | Slash-command completion palette. |
| `cli.tui.widgets.response_status` | 63 | — |
| `cli.tui.widgets.sidebar` | 248 | Sidebar widget: list of animas + activity feed. |
| `cli.tui.widgets.status_bar` | 160 | — |
| `cli.tui.widgets.thinking` | 98 | — |
| `cli.tui.widgets.tool_card` | 140 | — |
| `cli.tui.widgets.transcript` | 293 | — |

## `cli.tui.widgets`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `cli.tui.widgets` | 32 | — |

## `core`

—

| Module | Lines | docstring 1st line |
|---|---:|---|
| `core` | 7 | — |
| `core.auth_alert` | 87 | — |
| `core.credentials` | 288 | — |
| `core.exceptions` | 161 | — |
| `core.general_db` | 283 | Shared general database helpers. |
| `core.host_api` | 88 | — |
| `core.internal_api` | 51 | — |
| `core.jev_credits` | 273 | Jev (TypeSafe System One) prepaid-credit accounting for the usage dashboard. |
| `core.paths` | 262 | Centralized path resolution for AnimaWorks. |
| `core.project_threads` | 212 | — |
| `core.provider_cooldown` | 207 | — |
| `core.schemas` | 246 | — |
| `core.task_closure` | 142 | Task closure contract helpers. |
| `core.task_granularity` | 138 | — |
| `core.task_request_capture` | 223 | — |
| `core.time_utils` | 103 | — |
| `core.trust` | 436 | — |
| `core.urgent` | 128 | — |

## `core.activity`

Activity log recording, replay, and timeline display.

| Module | Lines | docstring 1st line |
|---|---:|---|
| `core.activity` | 24 | — |
| `core.activity.audit` | 290 | — |
| `core.activity.conversation` | 492 | — |
| `core.activity.event_export` | 33 | — |
| `core.activity.format` | 567 | — |
| `core.activity.logger` | 648 | — |
| `core.activity.models` | 202 | — |
| `core.activity.replay` | 537 | — |
| `core.activity.rotation` | 187 | — |
| `core.activity.runtime_context` | 30 | — |
| `core.activity.timeline` | 348 | — |

## `core.agent`

LLM agent execution, conversation control, and engine integration.

| Module | Lines | docstring 1st line |
|---|---:|---|
| `core.agent` | 23 | — |
| `core.agent.agent_core` | 325 | — |
| `core.agent.cycle` | 1801 | — |
| `core.agent.executor_factory` | 176 | — |
| `core.agent.priming` | 516 | — |
| `core.agent.prompt_log` | 151 | — |
| `core.agent.session_compactor` | 566 | Per-Anima × per-thread_id idle compaction timer management. |

## `core.anima`

Digital Anima lifecycle and runtime objects.

| Module | Lines | docstring 1st line |
|---|---:|---|
| `core.anima` | 23 | — |
| `core.anima._mixin_protocols（非公開）` | 130 | Structural host protocols for the compositional mixins. |
| `core.anima.admin` | 170 | — |
| `core.anima.asset_reconciler` | 764 | — |
| `core.anima.bootstrap_state` | 624 | — |
| `core.anima.digital_anima` | 694 | — |
| `core.anima.emotion_tag` | 84 | Shared emotion-tag extraction for LLM responses. |
| `core.anima.factory` | 885 | Anima creation factory: create new Digital Animas from templates, blank, or MD files. |
| `core.anima.heartbeat` | 1137 | — |
| `core.anima.image_artifacts` | 219 | — |
| `core.anima.inbox` | 1194 | — |
| `core.anima.inbox_overflow` | 100 | — |
| `core.anima.lifecycle` | 1876 | — |
| `core.anima.messaging` | 1392 | — |
| `core.anima.response_normalize` | 141 | — |
| `core.anima.roster` | 83 | — |
| `core.anima.settings_store` | 94 | — |
| `core.anima.skills_check` | 15 | — |

## `core.auth`

User authentication, sessions, and credential management.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.auth` | 7 | — |
| `core.auth.manager` | 192 | — |
| `core.auth.models` | 45 | — |

## `core.channels`

Shared send clients and token resolution for Slack, Discord, and Chatwork.

| Module | Lines | docstring 1st line |
|---|---:|---|
| `core.channels` | 1 | Shared clients and token resolution for external communication channels. |
| `core.channels.chatwork` | 33 | Central Chatwork message send client. |
| `core.channels.discord` | 393 | Central Discord REST API v10 client for channel messaging. |
| `core.channels.slack` | 97 | Central Slack Web API and incoming-webhook send client. |
| `core.channels.tokens` | 102 | Per-Anima external-channel token resolution. |

## `core.config`

Application configuration schemas, loading, validation, and migration.

| Module | Lines | First docstring line |
|---|---:|---|
| `core.config` | 42 | — |
| `core.config.anima_registry` | 313 | Anima registration in config.json: register, unregister, rename. |
| `core.config.antigravity_oauth` | 433 | — |
| `core.config.env_slots` | 92 | — |
| `core.config.file_access_policy` | 585 | — |
| `core.config.global_permissions` | 259 | — |
| `core.config.helper_models` | 498 | — |
| `core.config.io` | 437 | Configuration I/O: singleton cache, load, and save. |
| `core.config.jev` | 83 | Locate the Jev (TypeSafe System One) API key and its local spend ledger. |
| `core.config.local_llm` | 69 | Helpers for local Ollama-backed model defaults and role presets. |
| `core.config.migrate` | 208 | — |
| `core.config.model_catalog` | 209 | Static model catalog and per-request model override validation. |
| `core.config.model_config` | 893 | Model configuration resolution: load_model_config, penalties, max_tokens. |
| `core.config.model_discovery` | 647 | Dynamic discovery of the "mode + model" catalog from the installed CLIs. |
| `core.config.model_mode` | 587 | Model execution mode resolution for canonical S/C/D/G/X/A modes. |
| `core.config.models` | 103 | Central configuration module — facade re-exporting split modules. |
| `core.config.nanogpt` | 56 | Read nanoGPT credentials from the local source on each request. |
| `core.config.opencode_go` | 79 | — |
| `core.config.ops` | 203 | Application operations for reading and updating AnimaWorks configuration. |
| `core.config.resolver` | 175 | Configuration resolution: status.json merge with anima_defaults. |
| `core.config.schemas` | 1621 | Pydantic configuration schemas for AnimaWorks. |
| `core.config.vault` | 461 | Credential vault with PyNaCl SealedBox encryption. |

## `core.enclave`

Configuration models and startup security guards for isolated enclave mode.

| Module | Lines | First docstring line |
|---|---:|---|
| `core.enclave` | 54 | Enclave mode: an isolated runtime instance that bind to a dedicated socket. |
| `core.enclave.config` | 183 | Configuration models for enclave mode. |
| `core.enclave.egress.audit` | 62 | Audit logging for the egress pipeline. |
| `core.enclave.egress.config` | 113 | Configuration model for the egress pipeline. |
| `core.enclave.egress.fs` | 38 | Small filesystem helpers enforcing enclave file/directory permissions. |
| `core.enclave.egress.masker.dispatch` | 40 | Profile dispatch for the built-in masker. |
| `core.enclave.egress.masker.facts` | 162 | Rule-based masking of record facts. |
| `core.enclave.egress.masker.log_pii` | 115 | Masking of log/audit PII. |
| `core.enclave.egress.masker.ner` | 99 | Named-entity recognition masking using MeCab (fugashi + IPADIC). |
| `core.enclave.egress.models` | 57 | Data structures for the egress pipeline. |
| `core.enclave.egress.pipeline` | 96 | Egress pipeline: apply configured stages and fail closed on any error. |
| `core.enclave.egress.stages` | 236 | Stage implementations for the egress pipeline. |
| `core.enclave.gateway` | 521 | Gateway: the ingress point of an enclave instance. |
| `core.enclave.gateway_server` | 192 | Lifecycle and Unix-socket wiring for the enclave gateway. |
| `core.enclave.guards` | 250 | Startup guards for enclave mode. |
| `core.enclave.jobs` | 254 | Persistent query jobs for the enclave gateway. |
| `core.enclave.laravel_crypt` | 115 | Helpers for decrypting Laravel ``Crypt::encryptString`` payloads. |
| `core.enclave.ops` | 78 | Operational helpers for enclave health checks and audit summaries. |
| `core.enclave.raw_store` | 150 | Private storage for unmodified results read by enclave tools. |
| `core.enclave.secrets` | 128 | Read secrets from the enclave credentials store. |
| `core.enclave.ssm_tunnel` | 379 | SSM Session Manager port-forward tunnels for enclave SQL sources. |

## `core.enclave.egress`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.enclave.egress` | 29 | Egress pipeline: mask outgoing answers before they leave an enclave. |

## `core.enclave.egress.masker`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.enclave.egress.masker` | 19 | Built-in masker for the egress pipeline. |

## `core.execution`

Tool execution, command execution, and safety controls.

| Module | Lines | First docstring line |
|---|---:|---|
| `core.execution` | 70 | — |
| `core.execution._antigravity_llm（非公開）` | 658 | — |
| `core.execution._model_router（非公開）` | 148 | — |
| `core.execution._rtk_hook_bridge（非公開）` | 107 | Bridge script: Claude Code CLI Native Hook -> rtk rewrite. |
| `core.execution._shortterm_handoff（非公開）` | 145 | — |
| `core.execution._streaming（非公開）` | 368 | — |
| `core.execution._tool_summary（非公開）` | 103 | — |
| `core.execution.base` | 932 | — |
| `core.execution.busy_probe` | 68 | Congestion probe for self-hosted fallback models (vLLM ``/metrics``). |
| `core.execution.cli_stream` | 328 | — |
| `core.execution.engine_base` | 76 | — |
| `core.execution.engines.claude._sdk_hooks（非公開）` | 671 | — |
| `core.execution.engines.claude._sdk_interrupt（非公開）` | 112 | — |
| `core.execution.engines.claude._sdk_options（非公開）` | 653 | — |
| `core.execution.engines.claude._sdk_patch（非公開）` | 261 | — |
| `core.execution.engines.claude._sdk_security（非公開）` | 304 | — |
| `core.execution.engines.claude._sdk_session（非公開）` | 586 | — |
| `core.execution.engines.claude._sdk_stream（非公開）` | 519 | — |
| `core.execution.engines.claude.executor` | 867 | — |
| `core.execution.engines.codex.events` | 664 | — |
| `core.execution.engines.codex.executor` | 844 | — |
| `core.execution.engines.codex.setup` | 1039 | — |
| `core.execution.engines.cursor.executor` | 659 | — |
| `core.execution.engines.gemini.executor` | 461 | — |
| `core.execution.engines.grok.executor` | 1033 | — |
| `core.execution.engines.litellm._litellm_context（非公開）` | 532 | — |
| `core.execution.engines.litellm._litellm_tools（非公開）` | 422 | — |
| `core.execution.engines.litellm._llm_call（非公開）` | 326 | — |
| `core.execution.engines.litellm.executor` | 1068 | — |
| `core.execution.events` | 255 | — |
| `core.execution.fallback_activity` | 290 | Activity-log integration for ephemeral runtime model fallback. |
| `core.execution.github_identity` | 162 | GitHub identity resolution for executor environments. |
| `core.execution.loop_guards` | 412 | In-loop guard mechanisms for the self-hosted execution loops (Mode A/B). |
| `core.execution.mcp_env` | 39 | — |
| `core.execution.process_runner` | 184 | — |
| `core.execution.reminder` | 128 | — |
| `core.execution.session.engine_session` | 160 | — |
| `core.execution.session.session_context` | 114 | — |
| `core.execution.session.session_ids` | 116 | — |
| `core.execution.session.session_store` | 137 | — |
| `core.execution.session.session_types` | 73 | — |
| `core.execution.tool_evidence` | 182 | — |
| `core.execution.watchdog` | 139 | — |
| `core.execution.workspace_env` | 71 | — |

## `core.execution.engines`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.engines` | 6 | — |

## `core.execution.engines.claude`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.engines.claude` | 18 | — |

## `core.execution.engines.codex`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.engines.codex` | 6 | — |

## `core.execution.engines.cursor`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.engines.cursor` | 6 | — |

## `core.execution.engines.gemini`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.engines.gemini` | 6 | — |

## `core.execution.engines.grok`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.engines.grok` | 6 | — |

## `core.execution.engines.litellm`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.engines.litellm` | 6 | — |

## `core.execution.session`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.execution.session` | 7 | — |

## `core.i18n`

Translation catalogs and language selection.

| Module | Lines | First docstring line |
|---|---:|---|
| `core.i18n` | 135 | Lightweight i18n support for runtime strings. |
| `core.i18n.strings.communication` | 46 | Domain-specific i18n strings. |
| `core.i18n.strings.company` | 14 | Localized strings for company management. |
| `core.i18n.strings.config` | 856 | Domain-specific i18n strings. |
| `core.i18n.strings.discord` | 54 | — |
| `core.i18n.strings.execution` | 254 | Domain-specific i18n strings. |
| `core.i18n.strings.handler` | 400 | Domain-specific i18n strings (handler part 1). |
| `core.i18n.strings.handler_ext` | 393 | Domain-specific i18n strings (handler part 2). |
| `core.i18n.strings.lifecycle` | 104 | Domain-specific i18n strings. |
| `core.i18n.strings.memory` | 418 | Domain-specific i18n strings. |
| `core.i18n.strings.migrate` | 99 | — |
| `core.i18n.strings.misc` | 559 | Domain-specific i18n strings. |
| `core.i18n.strings.misc_routes` | 21 | Domain-specific i18n strings (legacy route modules). |
| `core.i18n.strings.models` | 70 | Localized CLI messages for model inspection. |
| `core.i18n.strings.phone` | 127 | — |
| `core.i18n.strings.room_manager` | 41 | i18n strings for meeting room manager. |
| `core.i18n.strings.server` | 251 | Domain-specific i18n strings. |
| `core.i18n.strings.supervisor` | 195 | Domain-specific i18n strings. |
| `core.i18n.strings.tmp` | 74 | — |
| `core.i18n.strings.tooling` | 125 | Domain-specific i18n strings (tool prompts and tooling). |
| `core.i18n.strings.tooling_schema` | 512 | Domain-specific i18n strings (schema.*). |
| `core.i18n.strings.tooling_schema_ext` | 167 | Domain-specific i18n strings (schema.* part 2). |
| `core.i18n.strings.zoom` | 26 | — |

## `core.i18n.strings`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.i18n.strings` | 65 | Merge all domain string modules into a single dict. |

## `core.infra`

Infrastructure features such as logs, databases, and caches.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.infra` | 6 | — |
| `core.infra.event_export` | 431 | — |
| `core.infra.execution_sdk_preflight` | 128 | — |
| `core.infra.gpu` | 173 | — |
| `core.infra.logging_config` | 650 | Centralized logging configuration for AnimaWorks. |
| `core.infra.runtime_init` | 429 | First-launch initialization: copy templates to runtime data directory. |
| `core.infra.startup_progress` | 191 | — |
| `core.infra.tmp_cleanup` | 254 | — |

## `core.integrations`

External service integrations and the implementation of animaworks-tool.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.integrations` | 79 | Core integration tool discovery and registry. |
| `core.integrations._anima_icon_url（非公開）` | 331 | Anima icon URL resolution — dashboard, outbound, Slack, notifications, tools, etc. |
| `core.integrations._async_compat（非公開）` | 41 | Async compatibility helpers for tools with synchronous HTTP clients. |
| `core.integrations._base（非公開）` | 200 | — |
| `core.integrations._cache（非公開）` | 172 | Shared SQLite message cache base class for communication tools. |
| `core.integrations._chatwork_cache（非公開）` | 324 | SQLite message cache for Chatwork offline search and unreplied detection. |
| `core.integrations._chatwork_client（非公開）` | 235 | HTTP client for the Chatwork v2 API. |
| `core.integrations._chatwork_cli（非公開）` | 633 | Standalone CLI entry point for the Chatwork tool. |
| `core.integrations._chatwork_identity（非公開）` | 76 | Chatwork identity and delegation resolution. |
| `core.integrations._chatwork_markdown（非公開）` | 162 | Markdown-to-Chatwork format conversion utilities. |
| `core.integrations._comm_cli（非公開）` | 64 | — |
| `core.integrations._discord_cache（非公開）` | 293 | SQLite message cache for Discord (offline search, sync state). |
| `core.integrations._discord_client（非公開）` | 47 | Backward-compatible Discord client import path. |
| `core.integrations._discord_cli（非公開）` | 349 | Standalone CLI entry point for Discord tools. |
| `core.integrations._discord_markdown（非公開）` | 164 | Discord markup helpers: plain-text cleanup and length limits. |
| `core.integrations._google_auth（非公開）` | 175 | Shared OAuth2 credential handling for Google integrations. |
| `core.integrations._image_clients（非公開）` | 97 | API clients and shared constants for image/3D generation. |
| `core.integrations._image_cli（非公開）` | 371 | CLI entry point for ``animaworks-tool image_gen``. |
| `core.integrations._image_glb（非公開）` | 489 | GLB/FBX asset conversion, optimisation, and compression. |
| `core.integrations._image_pipeline（非公開）` | 815 | ImageGenPipeline – orchestrates the full character asset generation. |
| `core.integrations._image_schemas（非公開）` | 42 | Tool schemas and CLI guide for image generation. |
| `core.integrations._retry（非公開）` | 170 | Shared retry/backoff utility for AnimaWorks tools. |
| `core.integrations._slack_cache（非公開）` | 435 | SQLite message cache for Slack (offline search, unreplied detection). |
| `core.integrations._slack_client（非公開）` | 308 | Slack Web API client with rate-limit retry and pagination. |
| `core.integrations._slack_cli（非公開）` | 308 | Standalone CLI entry point for Slack tools. |
| `core.integrations._slack_markdown（非公開）` | 240 | Slack markdown conversion and formatting utilities. |
| `core.integrations.aws_collector` | 408 | AnimaWorks AWS collector tool — ECS status, CloudWatch logs & metrics. |
| `core.integrations.bluesky` | 365 | Bluesky search tool for AnimaWorks. |
| `core.integrations.call_human` | 113 | — |
| `core.integrations.chatwork` | 281 | Chatwork integration for AnimaWorks. |
| `core.integrations.daily_ops_runner` | 131 | Daily Ops Dashboard runner control CLI. |
| `core.integrations.discord` | 366 | Discord integration for AnimaWorks. |
| `core.integrations.enclave` | 554 | Host-side tools for submitting and managing enclave ask jobs. |
| `core.integrations.enclave_aws` | 866 | Read-only AWS data tools for the enclave runtime. |
| `core.integrations.enclave_progress` | 111 | Tool for an anima to write interim progress onto an enclave ask job. |
| `core.integrations.enclave_records` | 222 | Read configured JSONL datasets from inside an enclave runtime. |
| `core.integrations.enclave_sql` | 396 | Read-only MySQL query tools for the enclave runtime. |
| `core.integrations.github` | 418 | AnimaWorks GitHub tool — gh CLI wrapper. |
| `core.integrations.gmail` | 1254 | AnimaWorks Gmail tool -- direct Gmail API access. |
| `core.integrations.google_calendar` | 615 | — |
| `core.integrations.google_sheets` | 470 | — |
| `core.integrations.google_tasks` | 445 | AnimaWorks Google Tasks tool -- Google Tasks API access. |
| `core.integrations.image.atlascloud` | 156 | Optional Atlas Cloud backend for character images and reference edits. |
| `core.integrations.image.codex` | 327 | Codex CLI image generation client (image_gen tool via local codex). |
| `core.integrations.image.constants` | 57 | URL constants, timeouts, and execution profiles for image/3D generation. |
| `core.integrations.image.diffusers_local` | 905 | Local Diffusers-backed image generation helpers. |
| `core.integrations.image.fal` | 243 | Fal.ai Flux Kontext and Flux Pro text-to-image API clients. |
| `core.integrations.image.meshy` | 311 | Meshy Image-to-3D, Rigging, and Animation API client. |
| `core.integrations.image.nanogpt` | 154 | NanoGPT API client for image generation (text-to-image / image-to-image). |
| `core.integrations.image.novelai` | 193 | NovelAI V4.5 API client for anime full-body image generation. |
| `core.integrations.image.openai` | 397 | Codex built-in GPT Image client for character portrait generation. |
| `core.integrations.image.prompts` | 197 | Prompt constants for bustup, chibi, and expression variants. |
| `core.integrations.image.utils` | 135 | Shared utilities for image/3D generation clients. |
| `core.integrations.image_gen` | 433 | Character image & 3-D model generation tool for AnimaWorks. |
| `core.integrations.local_llm` | 552 | AnimaWorks local LLM tool -- Ollama API client. |
| `core.integrations.notebooklm` | 627 | AnimaWorks NotebookLM tool -- Google NotebookLM integration. |
| `core.integrations.notion` | 861 | Notion integration for AnimaWorks. |
| `core.integrations.property_portal_scraper` | 763 | PROP-07 property sale portal monitor. |
| `core.integrations.slack` | 269 | Slack integration for AnimaWorks. |
| `core.integrations.transcribe` | 429 | AnimaWorks transcribe tool -- Whisper speech-to-text with LLM refinement. |
| `core.integrations.web_search` | 408 | Web Search tool for AnimaWorks. |
| `core.integrations.x_search` | 348 | X (Twitter) Search tool for AnimaWorks. |

## `core.integrations.image`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.integrations.image` | 90 | Image and 3D generation API clients and shared constants. |

## `core.lifecycle`

The startup, shutdown, and initialization lifecycle of an anima.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.lifecycle` | 17 | — |
| `core.lifecycle.knowledge_correction` | 127 | — |
| `core.lifecycle.system_consolidation` | 319 | — |
| `core.lifecycle.system_status` | 313 | — |

## `core.llm`

Common features for LLM error classification, rate control, and retry.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.llm` | 1 | LLM-related core utilities. |
| `core.llm.guard.backoff` | 42 | Backoff timing helpers for coordinated LLM retry. |
| `core.llm.guard.error_classifier` | 805 | Centralized LLM API error classification for coordinated recovery. |
| `core.llm.guard.rate_guard` | 341 | Cross-process LLM rate guard (fleet-wide circuit breaker). |
| `core.llm.helper_completion` | 145 | — |
| `core.llm.oneshot` | 951 | Shared LLM helper utilities for memory-management modules. |

## `core.llm.guard`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.llm.guard` | 1 | Provider-independent LLM retry and failure guards. |

## `core.mcp`

Model Context Protocol servers and clients.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.mcp` | 0 | — |
| `core.mcp.server` | 728 | — |
| `core.mcp.win_stdin` | 68 | Windows stdin line reader that never leaves a blocking ReadFile pending. |

## `core.memory`

Storage, search, and organization of conversation and episodic memory.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory` | 20 | — |
| `core.memory._llm_parse（非公開）` | 185 | Shared LLM-output parsing helpers for the memory pipeline. |
| `core.memory.config_reader` | 31 | — |
| `core.memory.conversation.compression` | 322 | Compression logic for conversation memory. |
| `core.memory.conversation.finalize` | 497 | Session finalization for conversation memory. |
| `core.memory.conversation.memory` | 349 | Conversation memory (会話記憶 / working memory) management. |
| `core.memory.conversation.models` | 149 | Data classes and constants for conversation memory. |
| `core.memory.conversation.prompt` | 270 | Prompt building functions for conversation memory. |
| `core.memory.conversation.shortterm` | 313 | Short-term memory (短期記憶) management. |
| `core.memory.conversation.state_update` | 49 | State update functions for conversation memory finalization. |
| `core.memory.conversation.streaming_journal` | 495 | — |
| `core.memory.facts.chunking` | 91 | — |
| `core.memory.facts.config` | 85 | — |
| `core.memory.facts.entity_index` | 452 | — |
| `core.memory.facts.extraction` | 529 | — |
| `core.memory.facts.extractor` | 431 | LLM-based entity and fact extraction pipeline. |
| `core.memory.facts.invalidation` | 515 | — |
| `core.memory.facts.invalidation_llm` | 154 | — |
| `core.memory.facts.live` | 578 | — |
| `core.memory.facts.observability` | 41 | — |
| `core.memory.facts.ontology` | 247 | Pydantic models for entity / fact extraction results. |
| `core.memory.facts.prompts.en` | 133 | English prompts for entity / fact extraction. |
| `core.memory.facts.prompts.ja` | 135 | Japanese prompts for entity / fact extraction. |
| `core.memory.facts.store` | 460 | — |
| `core.memory.frontmatter` | 430 | — |
| `core.memory.io` | 59 | — |
| `core.memory.maintenance.activity_compaction` | 479 | — |
| `core.memory.maintenance.background_review` | 565 | — |
| `core.memory.maintenance.consolidation` | 1190 | — |
| `core.memory.maintenance.cron_logger` | 159 | — |
| `core.memory.maintenance.cron_noop` | 241 | — |
| `core.memory.maintenance.distillation` | 548 | — |
| `core.memory.maintenance.forgetting` | 588 | — |
| `core.memory.maintenance.housekeeping` | 1970 | — |
| `core.memory.maintenance.hygiene` | 75 | — |
| `core.memory.maintenance.reconsolidation` | 669 | — |
| `core.memory.maintenance.resolution_tracker` | 60 | — |
| `core.memory.manager` | 701 | — |
| `core.memory.peer_profiles` | 37 | — |
| `core.memory.priming.channel_a` | 70 | — |
| `core.memory.priming.channel_b` | 539 | — |
| `core.memory.priming.channel_c` | 611 | — |
| `core.memory.priming.channel_e` | 205 | — |
| `core.memory.priming.channel_f` | 215 | — |
| `core.memory.priming.channel_g` | 113 | — |
| `core.memory.priming.constants` | 92 | — |
| `core.memory.priming.engine` | 503 | — |
| `core.memory.priming.format` | 124 | — |
| `core.memory.priming.items` | 59 | — |
| `core.memory.priming.outbound` | 142 | — |
| `core.memory.priming.policy` | 25 | — |
| `core.memory.priming.result` | 76 | — |
| `core.memory.priming.utils` | 284 | — |
| `core.memory.rag.cli_access` | 232 | CLI access to phase3 vector stores through the active owner or server. |
| `core.memory.rag.contextual_header` | 163 | — |
| `core.memory.rag.direct_access` | 24 | — |
| `core.memory.rag.embedding` | 393 | — |
| `core.memory.rag.endpoints` | 79 | — |
| `core.memory.rag.episode_time` | 46 | — |
| `core.memory.rag.exclusion` | 38 | — |
| `core.memory.rag.facts_chunker` | 100 | — |
| `core.memory.rag.index_signature` | 27 | Compatibility diagnostics for an existing embedding index signature. |
| `core.memory.rag.indexer` | 1593 | — |
| `core.memory.rag.indexer_delete` | 135 | — |
| `core.memory.rag.owner_lock` | 84 | Exclusive ownership lock for an anima's native vector database. |
| `core.memory.rag.repair.detect` | 743 | — |
| `core.memory.rag.repair.rebuild` | 401 | — |
| `core.memory.rag.repair.state` | 191 | Persistent repair-state helpers for RAG auto-repair. |
| `core.memory.rag.repair.types` | 27 | — |
| `core.memory.rag.retriever` | 809 | — |
| `core.memory.rag.shared_check_registry` | 140 | — |
| `core.memory.rag.shared_meta` | 162 | — |
| `core.memory.rag.sqlite_health` | 413 | — |
| `core.memory.rag.store` | 804 | — |
| `core.memory.rag.vector_client` | 497 | — |
| `core.memory.rag.vector_ops` | 88 | Conversion between vector API requests and the MemoryService wire format. |
| `core.memory.rag.vector_registry` | 160 | — |
| `core.memory.retrieval.bm25` | 1325 | — |
| `core.memory.retrieval.code_index` | 221 | — |
| `core.memory.retrieval.confidence_gate` | 39 | — |
| `core.memory.retrieval.entity` | 192 | — |
| `core.memory.retrieval.pipeline` | 92 | — |
| `core.memory.retrieval.query_expansion` | 496 | — |
| `core.memory.retrieval.rag_search` | 1149 | — |
| `core.memory.retrieval.reranker` | 262 | — |
| `core.memory.retrieval.rrf` | 107 | — |
| `core.memory.retrieval.search_metadata` | 108 | — |
| `core.memory.retrieval.time_expr` | 230 | — |
| `core.memory.retrieval.types` | 38 | — |
| `core.memory.retrieval.unified_search` | 722 | — |
| `core.memory.skill_metadata` | 49 | — |
| `core.memory.state_lock` | 96 | Process-safe locking for ``state/current_state.md`` updates. |
| `core.memory.task_verification` | 303 | — |

## `core.memory.conversation`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.conversation` | 23 | — |

## `core.memory.facts`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.facts` | 37 | — |

## `core.memory.facts.prompts`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.facts.prompts` | 3 | — |

## `core.memory.maintenance`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.maintenance` | 6 | — |

## `core.memory.priming`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.priming` | 54 | Priming layer - automatic memory retrieval (automatic recall). |

## `core.memory.rag`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.rag` | 23 | — |

## `core.memory.rag.repair`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.rag.repair` | 31 | — |

## `core.memory.retrieval`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.memory.retrieval` | 1 | Memory retrieval pipeline; import specific modules directly. |

## `core.messaging`

Message delivery between animas and with the outside world.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.messaging` | 6 | — |
| `core.messaging.board_fanout` | 98 | — |
| `core.messaging.discord_origin_threads` | 105 | — |
| `core.messaging.discord_webhooks` | 506 | — |
| `core.messaging.inbox_quiet_window` | 38 | — |
| `core.messaging.meeting_room_store` | 130 | — |
| `core.messaging.messenger` | 1084 | — |
| `core.messaging.outbound` | 448 | — |
| `core.messaging.outbound_auto` | 635 | — |
| `core.messaging.reply_grants` | 253 | — |
| `core.messaging.sender` | 32 | — |

## `core.migrations`

Gradual migration of runtime data formats.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.migrations` | 1 | Runtime migration framework; import specific modules directly. |
| `core.migrations.registry` | 149 | — |
| `core.migrations.steps` | 1212 | Migration step implementations for AnimaWorks runtime data. |
| `core.migrations.template_sync` | 137 | — |
| `core.migrations.tracker` | 143 | — |

## `core.notification`

Notification generation and delivery.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.notification` | 40 | — |
| `core.notification.channels.chatwork` | 79 | — |
| `core.notification.channels.discord` | 310 | — |
| `core.notification.channels.line` | 86 | — |
| `core.notification.channels.ntfy` | 87 | — |
| `core.notification.channels.slack` | 261 | — |
| `core.notification.channels.telegram` | 91 | — |
| `core.notification.channels.web` | 65 | — |
| `core.notification.interactive` | 612 | — |
| `core.notification.notifier` | 338 | — |
| `core.notification.reply_routing` | 467 | — |
| `core.notification.slack_names` | 67 | — |

## `core.notification.channels`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.notification.channels` | 7 | — |

## `core.org`

Organization models such as companies, departments, and roles.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.org` | 6 | — |
| `core.org.company` | 1212 | Company membership and cross-company boundary helpers. |
| `core.org.company_resources` | 86 | — |
| `core.org.hierarchy` | 39 | — |
| `core.org.org_sync` | 483 | — |
| `core.org.workspace` | 232 | — |

## `core.phone`

Speech synthesis, call status, and webhook management for the Twilio phone channel.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.phone` | 7 | — |
| `core.phone.alert` | 218 | — |
| `core.phone.audio_store` | 81 | — |
| `core.phone.session` | 66 | — |
| `core.phone.speech` | 83 | — |
| `core.phone.stream_tokens` | 101 | — |
| `core.phone.stream_transport` | 120 | — |
| `core.phone.twilio_client` | 194 | — |
| `core.phone.urgent` | 46 | — |

## `core.platform`

Integration layer that absorbs differences between execution engines and OSes.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.platform` | 4 | — |
| `core.platform.atomic_io` | 205 | — |
| `core.platform.claude_code` | 201 | — |
| `core.platform.codex` | 346 | — |
| `core.platform.cursor` | 60 | — |
| `core.platform.env` | 84 | — |
| `core.platform.fd_limits` | 60 | — |
| `core.platform.gemini` | 42 | — |
| `core.platform.grok` | 40 | — |
| `core.platform.locks` | 127 | — |
| `core.platform.pid` | 42 | — |
| `core.platform.process` | 392 | — |
| `core.platform.process_role` | 66 | Low-level environment access for process-role metadata. |
| `core.platform.processing_lease` | 349 | — |
| `core.platform.scratch` | 105 | — |
| `core.platform.state_writer` | 1017 | — |
| `core.platform.status_store` | 54 | — |
| `core.platform.subprocess_entries` | 23 | — |
| `core.platform.tasks` | 35 | — |

## `core.prompt`

Construction of system prompts and context.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.prompt` | 1 | Prompt construction package; import specific modules directly. |
| `core.prompt.assembler` | 307 | — |
| `core.prompt.builder` | 1332 | — |
| `core.prompt.context` | 493 | Context window usage tracker. |
| `core.prompt.messaging` | 147 | — |
| `core.prompt.org_context` | 378 | — |
| `core.prompt.sections` | 52 | — |

## `core.reports`

Validation, publishing, and review reminders for deliverable reports.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.reports` | 1 | Report generation modules managed in the AnimaWorks repository. |
| `core.reports.pending_review_surfacer` | 450 | Surface product drafts that are stuck in review-pending back to their reviewer. |
| `core.reports.property._listing_runs（非公開）` | 123 | Listing-run tracking shared by the daily property reports. |
| `core.reports.property.anjo_1k_product_draft` | 1222 | Create the Anjo 1K daily Products draft for Sakura review. |
| `core.reports.property.daily_sale_product_report` | 894 | Create the daily property sale portal Products draft for Sakura review. |
| `core.reports.property.sale_investment_analysis` | 289 | Evidence-linked preliminary investment reports for newly observed sale listings. |
| `core.reports.property.sale_property_registry` | 171 | Persistent physical-property numbers, independent of portal and asking price. |

## `core.reports.property`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.reports.property` | 1 | Property report generation jobs. |

## `core.runtime`

Runtime components of the anima main, inter-process communication, and task execution.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.runtime` | 1 | Runtime components owned by an individual Anima process. |
| `core.runtime.cron_diagnostics` | 85 | Registration-time diagnostics for cron schedules that waste LLM runs. |
| `core.runtime.cron_followup` | 169 | Shared command-cron follow-up policy for legacy and isolated runners. |
| `core.runtime.event_bus` | 88 | In-process event buffer for events emitted by an Anima main runner. |
| `core.runtime.inbox_rate_limiter` | 371 | Event-driven inbox wakeups and deferred trigger management. |
| `core.runtime.ipc` | 508 | IPC communication layer using JSON Lines over a platform-specific transport. |
| `core.runtime.ipc_v2` | 414 | Persistent duplex IPC v2 used between an Anima main and task runners. |
| `core.runtime.memory_probe` | 137 | — |
| `core.runtime.memory_service` | 774 | Anima-main-owned vector memory service. |
| `core.runtime.process_role` | 25 | Process role metadata shared by AnimaWorks process entry points. |
| `core.runtime.runner` | 1455 | Child process entry point for Anima subprocess. |
| `core.runtime.schedule_parser` | 538 | — |
| `core.runtime.scheduler_manager` | 1296 | APScheduler management for heartbeat and cron tasks. |
| `core.runtime.state_writer` | 27 | — |
| `core.runtime.streaming_handler` | 444 | Streaming IPC message handler. |
| `core.runtime.task_runner` | 1050 | Disposable task runner entry point. |
| `core.runtime.task_runner_supervisor` | 1445 | Anima-main-side lifecycle manager for disposable task runner processes. |
| `core.runtime.transport` | 240 | Transport helpers for IPC server/client communication. |

## `core.skills`

Skill discovery, loading, and execution support.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.skills` | 20 | — |
| `core.skills.activation` | 459 | — |
| `core.skills.activation_render` | 56 | — |
| `core.skills.activation_state` | 89 | — |
| `core.skills.autolearn` | 210 | — |
| `core.skills.autolearn_lifecycle` | 52 | — |
| `core.skills.cron_context` | 251 | — |
| `core.skills.curator` | 555 | — |
| `core.skills.dense` | 226 | — |
| `core.skills.guard` | 430 | — |
| `core.skills.hub` | 551 | — |
| `core.skills.hub_storage` | 63 | — |
| `core.skills.index` | 613 | — |
| `core.skills.ledger` | 404 | — |
| `core.skills.loader` | 176 | — |
| `core.skills.migration._common（非公開）` | 179 | — |
| `core.skills.migration.hermes` | 513 | — |
| `core.skills.migration.hermes_format` | 170 | — |
| `core.skills.migration.openclaw` | 220 | — |
| `core.skills.migration.report` | 125 | — |
| `core.skills.models` | 384 | — |
| `core.skills.pointer_rewriter` | 221 | — |
| `core.skills.policy` | 84 | — |
| `core.skills.probation_promotion` | 163 | — |
| `core.skills.promotion` | 604 | — |
| `core.skills.promotion_approval` | 85 | — |
| `core.skills.promotion_utils` | 148 | — |
| `core.skills.reference_rewriter` | 422 | — |
| `core.skills.router` | 505 | — |
| `core.skills.router_metadata` | 85 | — |
| `core.skills.sources.github` | 152 | — |
| `core.skills.sources.local` | 81 | — |
| `core.skills.sources.url` | 51 | — |
| `core.skills.trust` | 143 | — |
| `core.skills.trust_gate` | 22 | — |
| `core.skills.usage` | 202 | — |

## `core.skills.migration`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.skills.migration` | 14 | — |

## `core.skills.sources`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.skills.sources` | 1 | Skill source adapters; import specific modules directly. |

## `core.tasks`

Task registration, status management, and execution control.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.tasks` | 1 | Task queue, task board, delegated/background task execution and external task sources. |
| `core.tasks.autonomy_report` | 475 | — |
| `core.tasks.background` | 622 | — |
| `core.tasks.board.board_actions` | 260 | — |
| `core.tasks.board.housekeeping` | 188 | — |
| `core.tasks.board.models` | 39 | Pydantic models for the single TaskBoard view (read straight from TaskStore). |
| `core.tasks.board.notices` | 120 | — |
| `core.tasks.board.readiness` | 34 | Read-only boundary between legacy task files and canonical execution. |
| `core.tasks.board.tasks` | 1664 | Durable execution records; the single source of truth for the TaskBoard. |
| `core.tasks.board.view` | 119 | Single TaskBoard view built directly from the canonical TaskStore. |
| `core.tasks.dispatch` | 530 | — |
| `core.tasks.external.collector` | 211 | Multi-source external tasks collector with per-source fault isolation. |
| `core.tasks.external.models` | 47 | Data models for the external tasks snapshot store. |
| `core.tasks.external.sources.chatwork` | 228 | Chatwork external tasks collector (open my-tasks + unreplied To). |
| `core.tasks.external.sources.github` | 182 | GitHub external tasks collector via ``gh`` CLI. |
| `core.tasks.external.sources.gmail` | 124 | Gmail external tasks collector (unread inbox, last 7 days). |
| `core.tasks.external.sources.slack` | 184 | Slack external tasks collector (unreplied mentions via message cache). |
| `core.tasks.external.store` | 51 | Atomic JSON snapshot store for external tasks. |
| `core.tasks.pending_executor` | 1733 | Execute claimed TaskStore work in background lanes. |
| `core.tasks.queue` | 554 | — |
| `core.tasks.waiting` | 81 | — |
| `core.tasks.wake` | 70 | Cross-process wake fan-out for the PendingTaskExecutor. |

## `core.tasks.board`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.tasks.board` | 1 | Task board package; import specific modules directly. |

## `core.tasks.external`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.tasks.external` | 1 | External task collection package; import specific modules directly. |

## `core.tasks.external.sources`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.tasks.external.sources` | 8 | Per-source collectors for external tasks (stubs in this phase). |

## `core.text`

Text token estimation and truncation to fit within budget.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.text` | 1 | Shared text processing utilities. |
| `core.text.tokens` | 92 | — |

## `core.tooling`

Tool schemas, permissions, and execution infrastructure.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.tooling` | 1 | Tooling package; import specific modules to avoid eager handler loading. |
| `core.tooling._handler_protocols（非公開）` | 226 | Structural host protocols for the compositional mixins. |
| `core.tooling.codex_command_hook` | 31 | Core command-policy decision for Codex's PreToolUse hook. |
| `core.tooling.dispatch` | 256 | — |
| `core.tooling.handler` | 961 | — |
| `core.tooling.handler_base` | 335 | — |
| `core.tooling.handler_comms` | 1202 | — |
| `core.tooling.handler_create_anima` | 101 | — |
| `core.tooling.handler_delegation` | 318 | — |
| `core.tooling.handler_exec` | 374 | — |
| `core.tooling.handler_files` | 899 | — |
| `core.tooling.handler_memory` | 1435 | — |
| `core.tooling.handler_org` | 39 | — |
| `core.tooling.handler_org_dashboard` | 203 | — |
| `core.tooling.handler_perms` | 446 | — |
| `core.tooling.handler_skills` | 874 | — |
| `core.tooling.handler_subordinate_control` | 457 | — |
| `core.tooling.handler_workspace` | 279 | — |
| `core.tooling.heartbeat_snapshot` | 472 | — |
| `core.tooling.org_helpers` | 158 | — |
| `core.tooling.permissions` | 344 | — |
| `core.tooling.policy.action_gate` | 188 | — |
| `core.tooling.policy.command_policy` | 508 | — |
| `core.tooling.policy.registry` | 65 | — |
| `core.tooling.policy.schemas.admin` | 221 | — |
| `core.tooling.policy.schemas.builder` | 77 | — |
| `core.tooling.policy.schemas.channel` | 118 | — |
| `core.tooling.policy.schemas.converters` | 27 | — |
| `core.tooling.policy.schemas.loader` | 101 | — |
| `core.tooling.policy.schemas.memory` | 436 | — |
| `core.tooling.policy.schemas.notification` | 71 | — |
| `core.tooling.policy.schemas.session_todo` | 62 | — |
| `core.tooling.policy.schemas.skill` | 306 | — |
| `core.tooling.policy.schemas.supervisor` | 348 | — |
| `core.tooling.policy.schemas.task` | 209 | — |
| `core.tooling.policy.schemas.workspace` | 46 | — |
| `core.tooling.policy.submit_tasks` | 91 | — |
| `core.tooling.policy.surface` | 258 | — |
| `core.tooling.policy.tool_content` | 42 | — |
| `core.tooling.result_compressor` | 275 | — |
| `core.tooling.skill_creator` | 120 | — |
| `core.tooling.skill_promotion_tool` | 176 | — |
| `core.tooling.standalone` | 322 | — |
| `core.tooling.tool_context` | 17 | Shared runtime state passed to ToolHandler mixin delegates. |

## `core.tooling.policy`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.tooling.policy` | 1 | Tool schemas and policy primitives shared by execution and tooling. |

## `core.tooling.policy.schemas`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.tooling.policy.schemas` | 74 | Canonical tool schema definitions and format converters. |

## `core.usage`

Logging and aggregation of LLM usage and costs.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.usage` | 1 | Token usage accounting and per-Anima token budgets. |
| `core.usage.token_budget` | 73 | — |
| `core.usage.token_usage` | 605 | — |

## `core.voice`

Audio input/output and voice conversations.

| Module | Lines | First line of docstring |
|---|---:|---|
| `core.voice` | 7 | Voice chat subsystem — STT, TTS, and session orchestration. |
| `core.voice.audio_codec` | 161 | — |
| `core.voice.emotion_style` | 114 | — |
| `core.voice.front` | 385 | Voice front lane — lightweight speech-first chat path via a local LLM. |
| `core.voice.front_conversation` | 694 | Transport-agnostic front-lane conversation and delegation handling. |
| `core.voice.sentence_splitter` | 73 | Japanese-aware sentence splitting for streaming TTS. |
| `core.voice.session` | 1843 | Voice session — STT -> Chat -> TTS orchestration. |
| `core.voice.session_factory` | 66 | — |
| `core.voice.speech_text` | 332 | — |
| `core.voice.stt` | 145 | Voice STT — in-memory PCM transcription via faster-whisper. |
| `core.voice.stt_stream` | 300 | Streaming STT — rolling buffer + LocalAgreement-2 prefix commitment. |
| `core.voice.transport` | 21 | Transport protocol for voice-session output. |
| `core.voice.tts_base` | 63 | TTS abstract base — provider interface and config. |
| `core.voice.tts_elevenlabs` | 133 | ElevenLabs TTS provider — REST API streaming. |
| `core.voice.tts_factory` | 47 | TTS provider factory. |
| `core.voice.tts_gemini` | 220 | Gemini TTS provider — Gemini API ``streamGenerateContent`` (SSE streaming). |
| `core.voice.tts_irodori` | 79 | Irodori-TTS provider — HTTP API. |
| `core.voice.tts_sbv2` | 112 | Style-BERT-VITS2 / AivisSpeech TTS provider. |
| `core.voice.tts_voicevox` | 110 | VOICEVOX TTS provider — Engine HTTP API. |
| `core.voice.turn_detector` | 398 | — |
| `core.voice.voice_config` | 76 | — |

## `server`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `server` | 7 | — |
| `server.app` | 1435 | — |
| `server.avatar_upload` | 178 | — |
| `server.enclave_delivery` | 327 | Collect completed enclave ask jobs and deliver them to host inboxes. |
| `server.events` | 56 | — |
| `server.internal_auth` | 232 | — |
| `server.localhost` | 86 | — |
| `server.project_tasks` | 166 | Read Obsidian Projects DB task metadata for meeting setup. |
| `server.reload_manager` | 115 | — |
| `server.room_manager` | 787 | Meeting room lifecycle, orchestration, and minutes generation. |
| `server.stream_registry` | 489 | — |
| `server.usage_governor` | 1728 | — |
| `server.websocket` | 165 | — |

## `server.gateways`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `server.gateways` | 1 | Inbound chat/meeting gateways (Slack, Discord, Zoom, GitHub) run by the server. |
| `server.gateways.discord_channel_sync` | 355 | — |
| `server.gateways.discord_debate_threads` | 190 | Debate threads: Discord threads where several Animas discuss one record. |
| `server.gateways.discord_gateway` | 1047 | — |
| `server.gateways.github_gateway` | 534 | — |
| `server.gateways.slack_channel_sync` | 505 | — |
| `server.gateways.slack_interactive` | 239 | — |
| `server.gateways.slack_socket` | 1081 | — |
| `server.gateways.zoom_gateway` | 700 | — |

## `server.routes`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `server.routes` | 65 | — |
| `server.routes.animas` | 1231 | — |
| `server.routes.approve` | 89 | — |
| `server.routes.assets` | 2041 | — |
| `server.routes.auth` | 133 | — |
| `server.routes.channels` | 497 | — |
| `server.routes.chat` | 419 | — |
| `server.routes.chat_chunk_handler` | 289 | — |
| `server.routes.chat_emotion` | 8 | — |
| `server.routes.chat_images` | 80 | — |
| `server.routes.chat_models` | 50 | — |
| `server.routes.chat_producer` | 335 | — |
| `server.routes.chat_resume` | 114 | — |
| `server.routes.chat_ui_state` | 101 | — |
| `server.routes.chat_ws_effects` | 55 | — |
| `server.routes.ci_autofix` | 276 | — |
| `server.routes.config_routes` | 464 | — |
| `server.routes.external_tasks` | 261 | — |
| `server.routes.internal` | 1562 | — |
| `server.routes.logs_routes` | 217 | — |
| `server.routes.media_proxy` | 186 | — |
| `server.routes.memory_routes` | 450 | — |
| `server.routes.phone` | 404 | — |
| `server.routes.phone_stream` | 258 | — |
| `server.routes.room` | 1082 | Meeting room API routes with SSE streaming. |
| `server.routes.sessions` | 297 | — |
| `server.routes.setup` | 638 | — |
| `server.routes.skills` | 132 | — |
| `server.routes.sns_search` | 55 | — |
| `server.routes.system` | 1290 | — |
| `server.routes.taskboard` | 237 | — |
| `server.routes.usage_routes` | 1505 | — |
| `server.routes.users` | 280 | — |
| `server.routes.voice` | 223 | Voice chat WebSocket endpoint; per-Anima status.json settings use shared helpers. |
| `server.routes.webhooks` | 503 | — |
| `server.routes.websocket_route` | 46 | — |

## `server.services`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `server.services` | 5 | Server application services. |
| `server.services.anima_admin` | 7 | — |

## `server.supervisor`

—

| Module | Lines | First line of docstring |
|---|---:|---|
| `server.supervisor` | 23 | Server-level supervision APIs for managing Anima processes. |
| `server.supervisor._manager_protocols（非公開）` | 85 | Structural host protocols for the compositional mixins. |
| `server.supervisor._mgr_health（非公開）` | 496 | Health check mixin for ProcessSupervisor. |
| `server.supervisor._mgr_rag_repair（非公開）` | 268 | Supervised RAG repair mixin for ProcessSupervisor. |
| `server.supervisor._mgr_reconcile（非公開）` | 324 | Reconciliation mixin for ProcessSupervisor. |
| `server.supervisor._mgr_scheduler（非公開）` | 1511 | System scheduler mixin for ProcessSupervisor. |
| `server.supervisor.activity_schedule` | 100 | — |
| `server.supervisor.auto_updater` | 198 | — |
| `server.supervisor.manager` | 1328 | Process Supervisor - Manages lifecycle of Anima child processes. |
| `server.supervisor.process_handle` | 824 | Process handle for managing child Anima processes. |
| `server.supervisor.restart_state` | 169 | Unified restart state machine for ProcessSupervisor. |
