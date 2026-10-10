<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/modules.md -->
<!-- i18n: source-sha256=e7e5c9663efa9ba4d8570a1d21f347312344008a917ec0dbe3813046be0ba6a2 generated=2026-10-09 engine=local model=deepseek-v4-flash translator=2 -->

# 모듈 목록

`git ls-files core cli server`에서 추적 대상인 Python 파일을 나열합니다. 비공개 모듈에는 표시가 있습니다.

## `cli`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli` | 9 | — |
| `cli.__main__（非公開）` | 9 | — |
| `cli._anima_tool（非公開）` | 33 | — |
| `cli._gateway（非公開）` | 93 | — |
| `cli.codex_command_hook` | 64 | Codex의 ``PreToolUse`` 명령 정책 훅을 위한 CLI 어댑터. |
| `cli.demo` | 407 | 네이티브 ``animaworks demo`` 명령. |
| `cli.parser` | 867 | — |
| `cli.tool_dispatch` | 412 | 외부 도구, 작업 제출, 명령 별칭을 위한 CLI 디스패치. |

## `cli.commands`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.commands` | 5 | — |
| `cli.commands.anima` | 303 | — |
| `cli.commands.anima_mgmt` | 1172 | CLI commands for anima process management. |
| `cli.commands.board` | 144 | — |
| `cli.commands.company_cmd` | 272 | — |
| `cli.commands.config_cmd` | 238 | CLI handlers and interactive wizard for ``animaworks config``. |
| `cli.commands.cost_cmd` | 232 | — |
| `cli.commands.enclave_cmd` | 323 | Operational commands for enclave runtimes. |
| `cli.commands.import_cmd` | 88 | — |
| `cli.commands.index_cmd` | 380 | — |
| `cli.commands.init_cmd` | 155 | — |
| `cli.commands.internal_cmd` | 156 | — |
| `cli.commands.logs` | 209 | CLI commands for viewing anima logs. |
| `cli.commands.mcp_cmd` | 66 | — |
| `cli.commands.memory_cmd` | 56 | — |
| `cli.commands.messaging` | 86 | — |
| `cli.commands.migrate_cmd` | 114 | — |
| `cli.commands.models_cmd` | 303 | CLI commands for model information and management. |
| `cli.commands.optimize_assets` | 189 | — |
| `cli.commands.profile` | 332 | — |
| `cli.commands.rag_repair_status` | 147 | Status reporting for persistent RAG repair state. |
| `cli.commands.remake_cmd` | 272 | — |
| `cli.commands.repair_rag_cmd` | 135 | — |
| `cli.commands.server` | 848 | — |
| `cli.commands.skills` | 211 | — |
| `cli.commands.supervisor_cmd` | 91 | — |
| `cli.commands.task_cmd` | 539 | — |
| `cli.commands.task_store_cmd` | 258 | Operator-only, cohort-scoped task migration and current-state export. |
| `cli.commands.tmp_cmd` | 173 | — |
| `cli.commands.vault_cmd` | 309 | — |

## `cli.tui`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.tui` | 207 | — |
| `cli.tui.app` | 1936 | — |
| `cli.tui.client` | 394 | — |
| `cli.tui.commands` | 251 | — |
| `cli.tui.keybindings` | 90 | TUI용 키 바인딩 설정. |
| `cli.tui.markdown` | 535 | 터미널 대화 기록에 맞게 조정한 Markdown → Rich 렌더링 객체. |
| `cli.tui.session` | 216 | TUI 세션 유지 기능. |
| `cli.tui.sse` | 98 | — |
| `cli.tui.state` | 280 | TUI 사이드바, 활동 피드 및 팔레트의 클라이언트 전용 UI 상태. |
| `cli.tui.widgets.call_human` | 85 | 대화 기록에 표시되는 call_human 알림 카드. |
| `cli.tui.widgets.chat_input` | 152 | — |
| `cli.tui.widgets.palette` | 115 | 슬래시 명령 자동 완성 팔레트. |
| `cli.tui.widgets.response_status` | 63 | — |
| `cli.tui.widgets.sidebar` | 248 | 사이드바 위젯: Anima 목록 및 활동 피드. |
| `cli.tui.widgets.status_bar` | 160 | — |
| `cli.tui.widgets.thinking` | 98 | — |
| `cli.tui.widgets.tool_card` | 140 | — |
| `cli.tui.widgets.transcript` | 293 | — |

## `cli.tui.widgets`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.tui.widgets` | 32 | — |

## `core`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core` | 7 | — |
| `core.credentials` | 276 | — |
| `core.exceptions` | 149 | — |
| `core.host_api` | 88 | — |
| `core.internal_api` | 51 | — |
| `core.paths` | 218 | Centralized path resolution for AnimaWorks. |
| `core.schemas` | 240 | — |
| `core.time_utils` | 103 | — |
| `core.trust` | 433 | — |

## `core.activity`

활동 로그의 기록, 재생, 타임라인 표시.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.activity` | 24 | — |
| `core.activity.audit` | 290 | — |
| `core.activity.conversation` | 492 | — |
| `core.activity.event_export` | 33 | — |
| `core.activity.format` | 567 | — |
| `core.activity.logger` | 583 | — |
| `core.activity.models` | 202 | — |
| `core.activity.replay` | 537 | — |
| `core.activity.rotation` | 187 | — |
| `core.activity.runtime_context` | 30 | — |
| `core.activity.timeline` | 348 | — |

## `core.agent`

LLM 에이전트 실행, 대화 제어, 엔진 연동.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.agent` | 23 | — |
| `core.agent.agent_core` | 325 | — |
| `core.agent.cycle` | 1523 | — |
| `core.agent.executor_factory` | 176 | — |
| `core.agent.priming` | 493 | — |
| `core.agent.prompt_log` | 151 | — |
| `core.agent.session_compactor` | 566 | Per-Anima × per-thread_id idle compaction timer management. |

## `core.anima`

디지털 Anima의 라이프사이클과 런타임 객체.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.anima` | 23 | — |
| `core.anima._mixin_protocols（非公開）` | 130 | 컴포지셔널 믹스인을 위한 구조적 호스트 프로토콜. |
| `core.anima.admin` | 170 | — |
| `core.anima.asset_reconciler` | 764 | — |
| `core.anima.bootstrap_state` | 591 | — |
| `core.anima.digital_anima` | 693 | — |
| `core.anima.emotion_tag` | 84 | LLM 응답에서 감정 태그를 추출하는 공통 기능. |
| `core.anima.factory` | 842 | Anima 생성 팩토리: 템플릿, 빈 항목 또는 MD 파일에서 새 디지털 Anima를 생성합니다. |
| `core.anima.heartbeat` | 1022 | — |
| `core.anima.image_artifacts` | 219 | — |
| `core.anima.inbox` | 998 | — |
| `core.anima.inbox_overflow` | 100 | — |
| `core.anima.lifecycle` | 1662 | — |
| `core.anima.messaging` | 1384 | — |
| `core.anima.response_normalize` | 141 | — |
| `core.anima.roster` | 83 | — |
| `core.anima.settings_store` | 98 | — |
| `core.anima.skills_check` | 15 | — |

## `core.auth`

사용자 인증, 세션 및 인증 정보 관리.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.auth` | 7 | — |
| `core.auth.manager` | 192 | — |
| `core.auth.models` | 45 | — |

## `core.channels`

Slack, Discord, Chatwork의 공통 전송 클라이언트 및 토큰 해석.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.channels` | 1 | 외부 통신 채널을 위한 공유 클라이언트 및 토큰 해석. |
| `core.channels.chatwork` | 33 | 중앙 Chatwork 메시지 전송 클라이언트. |
| `core.channels.discord` | 346 | 채널 메시징을 위한 중앙 Discord REST API v10 클라이언트. |
| `core.channels.slack` | 97 | 중앙 Slack Web API 및 인커밍 웹훅 전송 클라이언트. |
| `core.channels.tokens` | 102 | Anima별 외부 채널 토큰 해석. |

## `core.config`

애플리케이션 설정의 스키마, 로드, 검증, 마이그레이션.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.config` | 42 | — |
| `core.config.anima_registry` | 313 | config.json에서의 Anima 등록: 등록, 등록 해제, 이름 변경. |
| `core.config.env_slots` | 92 | — |
| `core.config.file_access_policy` | 569 | — |
| `core.config.global_permissions` | 259 | — |
| `core.config.helper_models` | 498 | — |
| `core.config.io` | 317 | 설정 I/O: 싱글턴 캐시, 로드 및 저장. |
| `core.config.local_llm` | 69 | 로컬 Ollama 기반 모델 기본값 및 역할 프리셋을 위한 헬퍼. |
| `core.config.migrate` | 201 | — |
| `core.config.model_catalog` | 194 | 정적 모델 카탈로그 및 요청별 모델 오버라이드 검증. |
| `core.config.model_config` | 879 | 모델 설정 확인: load_model_config, penalties, max_tokens. |
| `core.config.model_discovery` | 530 | 설치된 CLI에서 "mode + model" 카탈로그를 동적으로 탐색. |
| `core.config.model_mode` | 448 | 표준 S/C/D/G/X/A 모드의 모델 실행 모드 확인. |
| `core.config.models` | 99 | 중앙 설정 모듈 — 분할된 모듈을 다시 내보내는 파사드. |
| `core.config.ops` | 203 | AnimaWorks 설정을 읽고 업데이트하는 애플리케이션 작업. |
| `core.config.resolver` | 160 | 설정 확인: anima_defaults와의 status.json 병합. |
| `core.config.schemas` | 1474 | AnimaWorks용 Pydantic 설정 스키마. |
| `core.config.vault` | 461 | PyNaCl SealedBox 암호화를 사용하는 자격 증명 볼트. |

## `core.enclave`

격리된 enclave 모드의 설정 모델과 시작 시 보안 가드.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.enclave` | 54 | Enclave mode: an isolated runtime instance that bind to a dedicated socket. |
| `core.enclave.config` | 154 | Configuration models for enclave mode. |
| `core.enclave.egress.audit` | 62 | Audit logging for the egress pipeline. |
| `core.enclave.egress.config` | 115 | Configuration model for the egress pipeline. |
| `core.enclave.egress.fs` | 38 | Small filesystem helpers enforcing enclave file/directory permissions. |
| `core.enclave.egress.masker.dispatch` | 36 | Profile dispatch for the built-in masker. |
| `core.enclave.egress.masker.facts` | 133 | Rule-based masking of record facts. |
| `core.enclave.egress.masker.log_pii` | 115 | Masking of log/audit PII. |
| `core.enclave.egress.masker.ner` | 97 | Named-entity recognition masking using MeCab (fugashi + IPADIC). |
| `core.enclave.egress.models` | 57 | Data structures for the egress pipeline. |
| `core.enclave.egress.pipeline` | 102 | Egress pipeline: apply configured stages and fail closed on any error. |
| `core.enclave.egress.stages` | 236 | Stage implementations for the egress pipeline. |
| `core.enclave.gateway` | 288 | Gateway: the ingress point of an enclave instance. |
| `core.enclave.gateway_server` | 186 | Lifecycle and Unix-socket wiring for the enclave gateway. |
| `core.enclave.guards` | 237 | Startup guards for enclave mode. |
| `core.enclave.laravel_crypt` | 115 | Helpers for decrypting Laravel encrypted strings. |
| `core.enclave.ops` | 78 | Operational helpers for enclave health checks and audit summaries. |
| `core.enclave.raw_store` | 150 | Private storage for unmodified enclave tool results. |
| `core.enclave.secrets` | 103 | Read secrets from the enclave credentials store. |
| `core.enclave.ssm_tunnel` | 306 | SSM Session Manager port-forward tunnels for enclave SQL sources. |

## `core.enclave.egress`

—

| 모듈 | 행 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.enclave.egress` | 29 | 이그레스 파이프라인: 엔클레이브를 벗어나기 전에 발신 답변을 마스킹. |

## `core.enclave.egress.masker`

—

| 모듈 | 행 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.enclave.egress.masker` | 19 | 이그레스 파이프라인용 기본 마스커. |

## `core.execution`

도구 실행, 명령 실행, 안전 제어.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution` | 57 | — |
| `core.execution._shortterm_handoff（非公開）` | 145 | — |
| `core.execution._streaming（非公開）` | 303 | — |
| `core.execution._tool_summary（非公開）` | 99 | — |
| `core.execution.base` | 915 | — |
| `core.execution.busy_probe` | 68 | 자체 호스팅 대체 모델(vLLM ``/metrics``)의 혼잡도 탐침. |
| `core.execution.cli_stream` | 328 | — |
| `core.execution.engine_base` | 76 | — |
| `core.execution.engines.claude._sdk_hooks（非公開）` | 652 | — |
| `core.execution.engines.claude._sdk_interrupt（非公開）` | 112 | — |
| `core.execution.engines.claude._sdk_options（非公開）` | 546 | — |
| `core.execution.engines.claude._sdk_patch（非公開）` | 261 | — |
| `core.execution.engines.claude._sdk_security（非公開）` | 299 | — |
| `core.execution.engines.claude._sdk_session（非公開）` | 586 | — |
| `core.execution.engines.claude._sdk_stream（非公開）` | 503 | — |
| `core.execution.engines.claude.executor` | 867 | — |
| `core.execution.engines.codex.events` | 664 | — |
| `core.execution.engines.codex.executor` | 844 | — |
| `core.execution.engines.codex.setup` | 943 | — |
| `core.execution.engines.cursor.executor` | 652 | — |
| `core.execution.engines.gemini.executor` | 458 | — |
| `core.execution.engines.grok.executor` | 1030 | — |
| `core.execution.engines.litellm._litellm_context（非公開）` | 526 | — |
| `core.execution.engines.litellm._litellm_tools（非公開）` | 404 | — |
| `core.execution.engines.litellm._llm_call（非公開）` | 326 | — |
| `core.execution.engines.litellm.executor` | 1048 | — |
| `core.execution.events` | 255 | — |
| `core.execution.fallback_activity` | 290 | 임시 런타임 모델 대체를 위한 활동 로그 통합. |
| `core.execution.github_identity` | 162 | 실행기 환경의 GitHub ID 확인. |
| `core.execution.loop_guards` | 411 | 자체 호스팅 실행 루프(Mode A/B)의 루프 내부 가드 메커니즘. |
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

## `core.execution.engines`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines` | 6 | — |

## `core.execution.engines.claude`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.claude` | 18 | — |

## `core.execution.engines.codex`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.codex` | 6 | — |

## `core.execution.engines.cursor`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.cursor` | 6 | — |

## `core.execution.engines.gemini`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.gemini` | 6 | — |

## `core.execution.engines.grok`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.grok` | 6 | — |

## `core.execution.engines.litellm`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.litellm` | 6 | — |

## `core.execution.session`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.session` | 7 | — |

## `core.i18n`

번역 카탈로그와 언어 선택.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.i18n` | 135 | Lightweight i18n support for runtime strings. |
| `core.i18n.strings.communication` | 46 | Domain-specific i18n strings. |
| `core.i18n.strings.company` | 14 | Localized strings for company management. |
| `core.i18n.strings.config` | 650 | Domain-specific i18n strings. |
| `core.i18n.strings.discord` | 28 | — |
| `core.i18n.strings.execution` | 205 | Domain-specific i18n strings. |
| `core.i18n.strings.handler` | 382 | Domain-specific i18n strings (handler part 1). |
| `core.i18n.strings.handler_ext` | 368 | Domain-specific i18n strings (handler part 2). |
| `core.i18n.strings.lifecycle` | 104 | Domain-specific i18n strings. |
| `core.i18n.strings.memory` | 418 | Domain-specific i18n strings. |
| `core.i18n.strings.migrate` | 99 | — |
| `core.i18n.strings.misc` | 467 | Domain-specific i18n strings. |
| `core.i18n.strings.misc_routes` | 21 | Domain-specific i18n strings (legacy route modules). |
| `core.i18n.strings.models` | 70 | Localized CLI messages for model inspection. |
| `core.i18n.strings.phone` | 127 | — |
| `core.i18n.strings.room_manager` | 29 | i18n strings for meeting room manager. |
| `core.i18n.strings.server` | 241 | Domain-specific i18n strings. |
| `core.i18n.strings.supervisor` | 91 | Domain-specific i18n strings. |
| `core.i18n.strings.tmp` | 74 | — |
| `core.i18n.strings.tooling` | 125 | Domain-specific i18n strings (tool prompts and tooling). |
| `core.i18n.strings.tooling_schema` | 488 | Domain-specific i18n strings (schema.*). |
| `core.i18n.strings.tooling_schema_ext` | 130 | Domain-specific i18n strings (schema.* part 2). |
| `core.i18n.strings.zoom` | 26 | — |

## `core.i18n.strings`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.i18n.strings` | 65 | 모든 도메인 문자열 모듈을 하나의 딕셔너리로 병합. |

## `core.infra`

로그, 데이터베이스, 캐시 등의 기반 기능.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.infra` | 6 | — |
| `core.infra.event_export` | 389 | — |
| `core.infra.execution_sdk_preflight` | 126 | — |
| `core.infra.gpu` | 173 | — |
| `core.infra.logging_config` | 530 | AnimaWorks의 중앙 집중식 로그 설정 |
| `core.infra.runtime_init` | 429 | 최초 실행 초기화: 템플릿을 런타임 데이터 디렉터리에 복사 |
| `core.infra.startup_progress` | 191 | — |
| `core.infra.tmp_cleanup` | 254 | — |

## `core.integrations`

외부 서비스 연동과 animaworks-tool의 구현.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations` | 79 | Core integration tool discovery and registry. |
| `core.integrations._anima_icon_url（非公開）` | 322 | Anima icon URL resolution — dashboard, outbound, Slack, notifications, tools, etc. |
| `core.integrations._async_compat（非公開）` | 41 | Async compatibility helpers for tools with synchronous HTTP clients. |
| `core.integrations._base（非公開）` | 158 | — |
| `core.integrations._cache（非公開）` | 172 | Shared SQLite message cache base class for communication tools. |
| `core.integrations._chatwork_cache（非公開）` | 324 | SQLite message cache for Chatwork offline search and unreplied detection. |
| `core.integrations._chatwork_client（非公開）` | 235 | HTTP client for the Chatwork v2 API. |
| `core.integrations._chatwork_cli（非公開）` | 633 | Standalone CLI entry point for the Chatwork tool. |
| `core.integrations._chatwork_identity（非公開）` | 76 | Chatwork identity and delegation resolution. |
| `core.integrations._chatwork_markdown（非公開）` | 162 | Markdown-to-Chatwork format conversion utilities. |
| `core.integrations._comm_cli（非公開）` | 64 | — |
| `core.integrations._discord_cache（非公開）` | 293 | SQLite message cache for Discord (offline search, sync state). |
| `core.integrations._discord_client（非公開）` | 47 | Backward-compatible Discord client import path. |
| `core.integrations._discord_cli（非公開）` | 297 | Standalone CLI entry point for Discord tools. |
| `core.integrations._discord_markdown（非公開）` | 138 | Discord markup helpers: plain-text cleanup and length limits. |
| `core.integrations._google_auth（非公開）` | 175 | Shared OAuth2 credential handling for Google integrations. |
| `core.integrations._image_clients（非公開）` | 93 | API clients and shared constants for image/3D generation. |
| `core.integrations._image_cli（非公開）` | 371 | CLI entry point for ``animaworks-tool image_gen``. |
| `core.integrations._image_glb（非公開）` | 473 | GLB/FBX asset conversion, optimisation, and compression. |
| `core.integrations._image_pipeline（非公開）` | 814 | ImageGenPipeline – orchestrates the full character asset generation. |
| `core.integrations._image_schemas（非公開）` | 42 | Tool schemas and CLI guide for image generation. |
| `core.integrations._retry（非公開）` | 170 | Shared retry/backoff utility for AnimaWorks tools. |
| `core.integrations._slack_cache（非公開）` | 435 | SQLite message cache for Slack (offline search, unreplied detection). |
| `core.integrations._slack_client（非公開）` | 308 | Slack Web API client with rate-limit retry and pagination. |
| `core.integrations._slack_cli（非公開）` | 308 | Standalone CLI entry point for Slack tools. |
| `core.integrations._slack_markdown（非公開）` | 240 | Slack markdown conversion and formatting utilities. |
| `core.integrations.aws_collector` | 408 | AnimaWorks AWS collector tool — ECS status, CloudWatch logs & metrics. |
| `core.integrations.call_human` | 113 | — |
| `core.integrations.chatwork` | 281 | Chatwork integration for AnimaWorks. |
| `core.integrations.discord` | 284 | Discord integration for AnimaWorks. |
| `core.integrations.enclave` | 213 | enclave_ask tool — ask an isolated enclave instance from the host side. |
| `core.integrations.enclave_aws` | 909 | Read-only AWS data tools for the enclave runtime. |
| `core.integrations.enclave_records` | 215 | Read configured JSONL datasets from inside an enclave runtime. |
| `core.integrations.enclave_sql` | 389 | Read-only MySQL query tools for the enclave runtime. |
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
| `core.integrations.image.novelai` | 193 | NovelAI V4.5 API client for anime full-body image generation. |
| `core.integrations.image.prompts` | 197 | Prompt constants for bustup, chibi, and expression variants. |
| `core.integrations.image.utils` | 135 | Shared utilities for image/3D generation clients. |
| `core.integrations.image_gen` | 425 | Character image & 3-D model generation tool for AnimaWorks. |
| `core.integrations.local_llm` | 552 | AnimaWorks local LLM tool -- Ollama API client. |
| `core.integrations.notion` | 862 | Notion integration for AnimaWorks. |
| `core.integrations.slack` | 262 | Slack integration for AnimaWorks. |
| `core.integrations.transcribe` | 429 | AnimaWorks transcribe tool -- Whisper speech-to-text with LLM refinement. |
| `core.integrations.web_search` | 408 | Web Search tool for AnimaWorks. |
| `core.integrations.x_search` | 348 | X (Twitter) Search tool for AnimaWorks. |

## `core.integrations.image`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations.image` | 85 | 이미지 및 3D 생성 API 클라이언트와 공통 상수. |

## `core.lifecycle`

anima의 시작, 종료, 초기화 라이프사이클.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.lifecycle` | 17 | — |
| `core.lifecycle.knowledge_correction` | 127 | — |
| `core.lifecycle.system_consolidation` | 308 | — |

## `core.llm`

LLM 오류 분류, 레이트 제어, 재시도를 위한 공통 기능.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.llm` | 1 | LLM 관련 핵심 유틸리티. |
| `core.llm.guard.backoff` | 42 | 조율된 LLM 재시도를 위한 백오프 타이밍 헬퍼. |
| `core.llm.guard.error_classifier` | 805 | 조율된 복구를 위한 중앙 집중식 LLM API 오류 분류. |
| `core.llm.guard.rate_guard` | 341 | 프로세스 간 LLM 레이트 가드(플릿 전체 회로 차단기). |
| `core.llm.helper_completion` | 145 | — |
| `core.llm.oneshot` | 927 | 메모리 관리 모듈을 위한 공통 LLM 헬퍼 유틸리티. |

## `core.llm.guard`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.llm.guard` | 1 | Provider-independent LLM retry and failure guards. |

## `core.mcp`

Model Context Protocol 서버와 클라이언트.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.mcp` | 0 | — |
| `core.mcp.server` | 714 | — |

## `core.memory`

대화·에피소드 기억의 저장, 검색, 정리.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory` | 20 | — |
| `core.memory._llm_parse（非公開）` | 185 | 메모리 파이프라인에서 LLM 출력을 파싱하기 위한 공통 헬퍼. |
| `core.memory.config_reader` | 31 | — |
| `core.memory.conversation.compression` | 322 | 대화 기억 압축 로직. |
| `core.memory.conversation.finalize` | 493 | 대화 기억의 세션 종료 처리. |
| `core.memory.conversation.memory` | 349 | 대화 기억(대화 기억 / 작업 기억) 관리. |
| `core.memory.conversation.models` | 149 | 대화 기억을 위한 데이터 클래스 및 상수. |
| `core.memory.conversation.prompt` | 270 | 대화 기억을 위한 프롬프트 구성 함수. |
| `core.memory.conversation.shortterm` | 313 | 단기 기억 관리. |
| `core.memory.conversation.state_update` | 49 | 대화 기억 종료 처리를 위한 상태 업데이트 함수. |
| `core.memory.conversation.streaming_journal` | 473 | — |
| `core.memory.facts.chunking` | 91 | — |
| `core.memory.facts.config` | 85 | — |
| `core.memory.facts.entity_index` | 452 | — |
| `core.memory.facts.extraction` | 526 | — |
| `core.memory.facts.extractor` | 431 | LLM 기반 엔터티 및 사실 추출 파이프라인. |
| `core.memory.facts.invalidation` | 515 | — |
| `core.memory.facts.invalidation_llm` | 154 | — |
| `core.memory.facts.live` | 578 | — |
| `core.memory.facts.observability` | 41 | — |
| `core.memory.facts.ontology` | 247 | 엔터티 / 사실 추출 결과를 위한 Pydantic 모델. |
| `core.memory.facts.prompts.en` | 133 | 엔터티 / 사실 추출용 영어 프롬프트. |
| `core.memory.facts.prompts.ja` | 135 | 엔터티 / 사실 추출용 일본어 프롬프트. |
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
| `core.memory.maintenance.housekeeping` | 1471 | — |
| `core.memory.maintenance.hygiene` | 75 | — |
| `core.memory.maintenance.reconsolidation` | 669 | — |
| `core.memory.maintenance.resolution_tracker` | 60 | — |
| `core.memory.manager` | 683 | — |
| `core.memory.peer_profiles` | 37 | — |
| `core.memory.priming.channel_a` | 70 | — |
| `core.memory.priming.channel_b` | 534 | — |
| `core.memory.priming.channel_c` | 610 | — |
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
| `core.memory.rag.cli_access` | 232 | 활성 소유자 또는 서버를 통해 phase3 벡터 저장소에 접근하는 CLI. |
| `core.memory.rag.contextual_header` | 163 | — |
| `core.memory.rag.direct_access` | 24 | — |
| `core.memory.rag.embedding` | 393 | — |
| `core.memory.rag.endpoints` | 79 | — |
| `core.memory.rag.episode_time` | 46 | — |
| `core.memory.rag.exclusion` | 38 | — |
| `core.memory.rag.facts_chunker` | 100 | — |
| `core.memory.rag.index_signature` | 27 | 기존 임베딩 인덱스 서명의 호환성 진단. |
| `core.memory.rag.indexer` | 1593 | — |
| `core.memory.rag.indexer_delete` | 135 | — |
| `core.memory.rag.owner_lock` | 84 | anima의 네이티브 벡터 데이터베이스를 위한 독점 소유권 잠금. |
| `core.memory.rag.repair.detect` | 743 | — |
| `core.memory.rag.repair.rebuild` | 401 | — |
| `core.memory.rag.repair.state` | 191 | RAG 자동 복구를 위한 영구 복구 상태 헬퍼. |
| `core.memory.rag.repair.types` | 27 | — |
| `core.memory.rag.retriever` | 809 | — |
| `core.memory.rag.shared_check_registry` | 140 | — |
| `core.memory.rag.shared_meta` | 162 | — |
| `core.memory.rag.sqlite_health` | 359 | — |
| `core.memory.rag.store` | 783 | — |
| `core.memory.rag.vector_client` | 497 | — |
| `core.memory.rag.vector_ops` | 82 | 벡터 API 요청과 MemoryService 와이어 형식 간 변환. |
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
| `core.memory.state_lock` | 96 | ``state/current_state.md`` 업데이트를 위한 프로세스 안전 잠금. |

## `core.memory.conversation`

—

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.memory.conversation` | 23 | — |

## `core.memory.facts`

—

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.memory.facts` | 37 | — |

## `core.memory.facts.prompts`

—

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.memory.facts.prompts` | 3 | — |

## `core.memory.maintenance`

—

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.memory.maintenance` | 6 | — |

## `core.memory.priming`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.priming` | 54 | 프라이밍 계층 - 자동 기억 회상. |

## `core.memory.rag`

—

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.memory.rag` | 23 | — |

## `core.memory.rag.repair`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.rag.repair` | 31 | — |

## `core.memory.retrieval`

—

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.memory.retrieval` | 1 | 메모리 검색 파이프라인. 모듈을 직접 지정해 임포트하세요. |

## `core.messaging`

Anima 간 및 외부 메시지 전달.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.messaging` | 6 | — |
| `core.messaging.board_fanout` | 95 | — |
| `core.messaging.discord_webhooks` | 296 | — |
| `core.messaging.meeting_room_store` | 130 | — |
| `core.messaging.messenger` | 1082 | — |
| `core.messaging.outbound` | 408 | — |
| `core.messaging.outbound_auto` | 377 | — |
| `core.messaging.reply_grants` | 253 | — |
| `core.messaging.sender` | 32 | — |

## `core.migrations`

런타임 데이터 형식의 단계적 마이그레이션.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.migrations` | 1 | 런타임 마이그레이션 프레임워크. 특정 모듈을 직접 임포트하세요. |
| `core.migrations.registry` | 149 | — |
| `core.migrations.steps` | 1228 | AnimaWorks 런타임 데이터를 위한 마이그레이션 단계 구현. |
| `core.migrations.template_sync` | 137 | — |
| `core.migrations.tracker` | 143 | — |

## `core.notification`

알림 생성 및 전달.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.notification` | 40 | — |
| `core.notification.channels.chatwork` | 79 | — |
| `core.notification.channels.discord` | 251 | — |
| `core.notification.channels.line` | 86 | — |
| `core.notification.channels.ntfy` | 87 | — |
| `core.notification.channels.slack` | 261 | — |
| `core.notification.channels.telegram` | 91 | — |
| `core.notification.channels.web` | 65 | — |
| `core.notification.interactive` | 612 | — |
| `core.notification.notifier` | 238 | — |
| `core.notification.reply_routing` | 467 | — |
| `core.notification.slack_names` | 67 | — |

## `core.notification.channels`

—

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.notification.channels` | 7 | — |

## `core.org`

회사, 부서, 역할 등의 조직 모델.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.org` | 6 | — |
| `core.org.company` | 1212 | Company membership and cross-company boundary helpers. |
| `core.org.company_resources` | 86 | — |
| `core.org.hierarchy` | 39 | — |
| `core.org.org_sync` | 482 | — |
| `core.org.workspace` | 232 | — |

## `core.phone`

Twilio 전화 채널의 음성 합성, 통화 상태 및 웹훅 관리.

| 모듈 | 행 수 | docstring 첫 줄 |
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

실행 엔진이나 OS별 차이를 흡수하는 연동 계층.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.platform` | 4 | — |
| `core.platform.atomic_io` | 207 | — |
| `core.platform.claude_code` | 194 | — |
| `core.platform.codex` | 245 | — |
| `core.platform.cursor` | 60 | — |
| `core.platform.env` | 84 | — |
| `core.platform.fd_limits` | 60 | — |
| `core.platform.gemini` | 42 | — |
| `core.platform.grok` | 40 | — |
| `core.platform.locks` | 125 | — |
| `core.platform.pid` | 42 | — |
| `core.platform.process` | 327 | — |
| `core.platform.process_role` | 66 | 프로세스 역할 메타데이터를 위한 저수준 환경 접근. |
| `core.platform.processing_lease` | 344 | — |
| `core.platform.state_writer` | 1012 | — |
| `core.platform.status_store` | 54 | — |
| `core.platform.subprocess_entries` | 23 | — |
| `core.platform.tasks` | 35 | — |

## `core.prompt`

시스템 프롬프트와 컨텍스트 구축.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.prompt` | 1 | Prompt construction package; import specific modules directly. |
| `core.prompt.assembler` | 307 | — |
| `core.prompt.builder` | 1287 | — |
| `core.prompt.context` | 486 | Context window usage tracker. |
| `core.prompt.messaging` | 147 | — |
| `core.prompt.org_context` | 378 | — |
| `core.prompt.sections` | 52 | — |

## `core.runtime`

Anima 메인 런타임 구성 요소, 프로세스 간 통신, 작업 실행.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.runtime` | 1 | 개별 Anima 프로세스가 소유하는 런타임 구성 요소. |
| `core.runtime.cron_followup` | 45 | 레거시 및 격리된 실행기에서 공유하는 명령 크론 후속 정책. |
| `core.runtime.event_bus` | 88 | Anima 메인 실행기가 발생시킨 이벤트를 위한 프로세스 내 버퍼. |
| `core.runtime.inbox_rate_limiter` | 270 | 이벤트 기반 받은 편지함 깨우기 및 지연된 트리거 관리. |
| `core.runtime.ipc` | 508 | 플랫폼별 전송 방식을 통한 JSON Lines 기반 IPC 통신 계층. |
| `core.runtime.ipc_v2` | 414 | Anima 메인과 작업 실행기 사이에 사용되는 영속적 양방향 IPC v2. |
| `core.runtime.memory_service` | 774 | Anima 메인이 소유하는 벡터 메모리 서비스. |
| `core.runtime.process_role` | 25 | AnimaWorks 프로세스 진입점 간에 공유되는 프로세스 역할 메타데이터. |
| `core.runtime.runner` | 1389 | Anima 하위 프로세스의 자식 프로세스 진입점. |
| `core.runtime.schedule_parser` | 484 | — |
| `core.runtime.scheduler_manager` | 827 | 하트비트 및 크론 작업을 위한 APScheduler 관리. |
| `core.runtime.state_writer` | 27 | — |
| `core.runtime.streaming_handler` | 441 | 스트리밍 IPC 메시지 처리기. |
| `core.runtime.task_runner` | 1042 | 일회용 작업 실행기 진입점. |
| `core.runtime.task_runner_supervisor` | 1386 | 일회용 작업 실행기 프로세스를 위한 Anima 메인 측 수명 주기 관리자. |
| `core.runtime.transport` | 240 | IPC server/client 통신을 위한 전송 도우미. |

## `core.skills`

스킬 검색, 로드 및 실행 지원.

| 모듈 | 행 수 | docstring 첫 줄 |
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
| `core.skills.router` | 504 | — |
| `core.skills.router_metadata` | 85 | — |
| `core.skills.sources.github` | 152 | — |
| `core.skills.sources.local` | 81 | — |
| `core.skills.sources.url` | 51 | — |
| `core.skills.trust` | 143 | — |
| `core.skills.trust_gate` | 22 | — |
| `core.skills.usage` | 202 | — |

## `core.skills.migration`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.skills.migration` | 14 | — |

## `core.skills.sources`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.skills.sources` | 1 | Skill source adapters; import specific modules directly. |

## `core.tasks`

작업 등록, 상태 관리 및 실행 제어.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks` | 1 | 작업 큐, TaskBoard, delegated/background 작업 실행 및 외부 작업 소스. |
| `core.tasks.background` | 618 | — |
| `core.tasks.board.board_actions` | 239 | — |
| `core.tasks.board.housekeeping` | 188 | — |
| `core.tasks.board.models` | 39 | 단일 TaskBoard 뷰용 Pydantic 모델(TaskStore에서 직접 읽음). |
| `core.tasks.board.notices` | 120 | — |
| `core.tasks.board.readiness` | 31 | 기존 작업 파일과 정식 실행 간 읽기 전용 경계. |
| `core.tasks.board.tasks` | 1321 | 영속 실행 레코드; TaskBoard의 단일 기준 데이터. |
| `core.tasks.board.view` | 119 | 정식 TaskStore에서 직접 구성한 단일 TaskBoard 뷰. |
| `core.tasks.dispatch` | 346 | — |
| `core.tasks.external.collector` | 211 | 소스별 장애 격리를 지원하는 다중 소스 외부 작업 수집기. |
| `core.tasks.external.models` | 47 | 외부 작업 스냅샷 저장소용 데이터 모델. |
| `core.tasks.external.sources.chatwork` | 228 | Chatwork 외부 작업 수집기(열린 my-tasks 및 미응답 To). |
| `core.tasks.external.sources.github` | 182 | ``gh`` CLI를 통한 GitHub 외부 작업 수집기. |
| `core.tasks.external.sources.gmail` | 124 | Gmail 외부 작업 수집기(읽지 않은 받은편지함, 최근 7일). |
| `core.tasks.external.sources.slack` | 184 | Slack 외부 작업 수집기(메시지 캐시를 통한 미응답 멘션). |
| `core.tasks.external.store` | 51 | 외부 작업용 원자적 JSON 스냅샷 저장소. |
| `core.tasks.pending_executor` | 1565 | 요청이 접수된 TaskStore 작업을 백그라운드 레인에서 실행합니다. |
| `core.tasks.queue` | 500 | — |
| `core.tasks.wake` | 70 | PendingTaskExecutor를 위한 프로세스 간 깨우기 이벤트 전달. |

## `core.tasks.board`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks.board` | 1 | Task board package; import specific modules directly. |

## `core.tasks.external`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks.external` | 1 | External task collection package; import specific modules directly. |

## `core.tasks.external.sources`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks.external.sources` | 8 | Per-source collectors for external tasks (stubs in this phase). |

## `core.text`

텍스트의 토큰 예상과 예산 내 잘라내기.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.text` | 1 | Shared text processing utilities. |
| `core.text.tokens` | 92 | — |

## `core.tooling`

도구의 스키마, 권한, 실행 기반.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tooling` | 1 | Tooling package; import specific modules to avoid eager handler loading. |
| `core.tooling._handler_protocols（非公開）` | 224 | Structural host protocols for the compositional mixins. |
| `core.tooling.codex_command_hook` | 31 | Core command-policy decision for Codex's PreToolUse hook. |
| `core.tooling.dispatch` | 256 | — |
| `core.tooling.handler` | 907 | — |
| `core.tooling.handler_base` | 335 | — |
| `core.tooling.handler_comms` | 996 | — |
| `core.tooling.handler_create_anima` | 101 | — |
| `core.tooling.handler_delegation` | 262 | — |
| `core.tooling.handler_exec` | 345 | — |
| `core.tooling.handler_files` | 899 | — |
| `core.tooling.handler_memory` | 1434 | — |
| `core.tooling.handler_org` | 39 | — |
| `core.tooling.handler_org_dashboard` | 203 | — |
| `core.tooling.handler_perms` | 446 | — |
| `core.tooling.handler_skills` | 837 | — |
| `core.tooling.handler_subordinate_control` | 457 | — |
| `core.tooling.handler_workspace` | 279 | — |
| `core.tooling.org_helpers` | 158 | — |
| `core.tooling.permissions` | 344 | — |
| `core.tooling.policy.action_gate` | 188 | — |
| `core.tooling.policy.command_policy` | 455 | — |
| `core.tooling.policy.registry` | 64 | — |
| `core.tooling.policy.schemas.admin` | 221 | — |
| `core.tooling.policy.schemas.builder` | 77 | — |
| `core.tooling.policy.schemas.channel` | 118 | — |
| `core.tooling.policy.schemas.converters` | 27 | — |
| `core.tooling.policy.schemas.loader` | 101 | — |
| `core.tooling.policy.schemas.memory` | 228 | — |
| `core.tooling.policy.schemas.notification` | 71 | — |
| `core.tooling.policy.schemas.session_todo` | 62 | — |
| `core.tooling.policy.schemas.skill` | 306 | — |
| `core.tooling.policy.schemas.supervisor` | 340 | — |
| `core.tooling.policy.schemas.task` | 180 | — |
| `core.tooling.policy.schemas.workspace` | 46 | — |
| `core.tooling.policy.submit_tasks` | 91 | — |
| `core.tooling.policy.surface` | 247 | — |
| `core.tooling.policy.tool_content` | 42 | — |
| `core.tooling.skill_creator` | 120 | — |
| `core.tooling.skill_promotion_tool` | 176 | — |
| `core.tooling.standalone` | 322 | — |
| `core.tooling.tool_context` | 17 | Shared runtime state passed to ToolHandler mixin delegates. |

## `core.tooling.policy`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tooling.policy` | 1 | Tool schemas and policy primitives shared by execution and tooling. |

## `core.tooling.policy.schemas`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tooling.policy.schemas` | 70 | Canonical tool schema definitions and format converters. |

## `core.usage`

LLM 사용량과 비용의 기록·집계.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.usage` | 1 | Token usage accounting and per-Anima token budgets. |
| `core.usage.token_budget` | 55 | — |
| `core.usage.token_usage` | 587 | — |

## `core.voice`

음성 입출력 및 음성 대화.

| 모듈 | 줄 수 | docstring 첫 줄 |
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

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `server` | 7 | — |
| `server.app` | 1440 | — |
| `server.events` | 56 | — |
| `server.internal_auth` | 232 | — |
| `server.localhost` | 86 | — |
| `server.reload_manager` | 115 | — |
| `server.room_manager` | 542 | 회의실의 수명 주기, 오케스트레이션 및 회의록 생성. |
| `server.stream_registry` | 489 | — |
| `server.websocket` | 165 | — |

## `server.gateways`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server.gateways` | 1 | Inbound chat/meeting gateways (Slack, Discord, Zoom, GitHub) run by the server. |
| `server.gateways.discord_channel_sync` | 278 | — |
| `server.gateways.discord_gateway` | 727 | — |
| `server.gateways.github_gateway` | 534 | — |
| `server.gateways.slack_channel_sync` | 505 | — |
| `server.gateways.slack_interactive` | 239 | — |
| `server.gateways.slack_socket` | 1081 | — |
| `server.gateways.zoom_gateway` | 700 | — |

## `server.routes`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server.routes` | 63 | — |
| `server.routes.animas` | 1205 | — |
| `server.routes.approve` | 89 | — |
| `server.routes.assets` | 1456 | — |
| `server.routes.auth` | 133 | — |
| `server.routes.channels` | 496 | — |
| `server.routes.chat` | 419 | — |
| `server.routes.chat_chunk_handler` | 289 | — |
| `server.routes.chat_emotion` | 8 | — |
| `server.routes.chat_images` | 80 | — |
| `server.routes.chat_models` | 50 | — |
| `server.routes.chat_producer` | 335 | — |
| `server.routes.chat_resume` | 114 | — |
| `server.routes.chat_ui_state` | 101 | — |
| `server.routes.chat_ws_effects` | 55 | — |
| `server.routes.config_routes` | 450 | — |
| `server.routes.external_tasks` | 261 | — |
| `server.routes.internal` | 1510 | — |
| `server.routes.logs_routes` | 217 | — |
| `server.routes.media_proxy` | 186 | — |
| `server.routes.memory_routes` | 450 | — |
| `server.routes.phone` | 404 | — |
| `server.routes.phone_stream` | 258 | — |
| `server.routes.room` | 443 | SSE 스트리밍을 사용하는 회의실 API 라우트. |
| `server.routes.sessions` | 297 | — |
| `server.routes.setup` | 603 | — |
| `server.routes.skills` | 132 | — |
| `server.routes.system` | 1170 | — |
| `server.routes.taskboard` | 237 | — |
| `server.routes.usage_routes` | 844 | — |
| `server.routes.users` | 280 | — |
| `server.routes.voice` | 223 | 음성 채팅 WebSocket 엔드포인트; Anima별 status.json 설정은 공용 헬퍼를 사용. |
| `server.routes.webhooks` | 503 | — |
| `server.routes.websocket_route` | 46 | — |

## `server.services`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server.services` | 5 | Server application services. |
| `server.services.anima_admin` | 7 | — |

## `server.supervisor`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `server.supervisor` | 23 | Anima 프로세스 관리를 위한 서버 수준 감독 API. |
| `server.supervisor._manager_protocols（非公開）` | 85 | 구성형 믹스인을 위한 구조적 호스트 프로토콜. |
| `server.supervisor._mgr_health（非公開）` | 470 | ProcessSupervisor용 상태 점검 믹스인. |
| `server.supervisor._mgr_rag_repair（非公開）` | 268 | ProcessSupervisor용 감독형 RAG 복구 믹스인. |
| `server.supervisor._mgr_reconcile（非公開）` | 320 | ProcessSupervisor용 조정 믹스인. |
| `server.supervisor._mgr_scheduler（非公開）` | 1245 | ProcessSupervisor용 시스템 스케줄러 믹스인. |
| `server.supervisor.activity_schedule` | 100 | — |
| `server.supervisor.auto_updater` | 198 | — |
| `server.supervisor.manager` | 1148 | 프로세스 감독자 - Anima 자식 프로세스의 수명 주기를 관리합니다. |
| `server.supervisor.process_handle` | 768 | 자식 Anima 프로세스를 관리하기 위한 프로세스 핸들. |
| `server.supervisor.restart_state` | 169 | ProcessSupervisor용 통합 재시작 상태 머신. |
