<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/modules.md -->
<!-- i18n: source-sha256=d790919e7296357f859d0ba26618944dcec7d52268e56bb8c50e2fb70e167d3f generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

# 모듈 목록

`git ls-files core cli server`에서 추적 대상인 Python 파일을 나열합니다. 비공개 모듈에는 표시가 있습니다.

## `cli`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli` | 9 | — |
| `cli.__main__（非公開）` | 9 | — |
| `cli._gateway（非公開）` | 93 | — |
| `cli.demo` | 394 | Native ``animaworks demo`` command. |
| `cli.parser` | 842 | — |
| `cli.tool_dispatch` | 91 | — |

## `cli.commands`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.commands` | 5 | — |
| `cli.commands.anima` | 214 | — |
| `cli.commands.anima_mgmt` | 1147 | anima 프로세스 관리를 위한 CLI 명령어. |
| `cli.commands.board` | 192 | — |
| `cli.commands.company_cmd` | 226 | — |
| `cli.commands.cost_cmd` | 232 | — |
| `cli.commands.import_cmd` | 88 | — |
| `cli.commands.index_cmd` | 380 | — |
| `cli.commands.init_cmd` | 136 | — |
| `cli.commands.internal_cmd` | 349 | — |
| `cli.commands.logs` | 209 | anima 로그 조회를 위한 CLI 명령어. |
| `cli.commands.mcp_cmd` | 66 | — |
| `cli.commands.memory_cmd` | 56 | — |
| `cli.commands.messaging` | 144 | — |
| `cli.commands.migrate_cmd` | 114 | — |
| `cli.commands.models_cmd` | 219 | 모델 정보 및 관리를 위한 CLI 명령어. |
| `cli.commands.optimize_assets` | 189 | — |
| `cli.commands.profile` | 332 | — |
| `cli.commands.rag_repair_status` | 147 | 지속형 RAG 복구 상태에 대한 상태 보고. |
| `cli.commands.remake_cmd` | 272 | — |
| `cli.commands.repair_rag_cmd` | 135 | — |
| `cli.commands.server` | 826 | — |
| `cli.commands.skills` | 211 | — |
| `cli.commands.supervisor_cmd` | 110 | — |
| `cli.commands.task_cmd` | 569 | — |
| `cli.commands.task_store_cmd` | 258 | 운영자 전용, 코호트 범위 작업 마이그레이션 및 현재 상태 내보내기. |
| `cli.commands.tmp_cmd` | 173 | — |
| `cli.commands.vault_cmd` | 248 | — |

## `cli.tui`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.tui` | 207 | — |
| `cli.tui.app` | 1820 | — |
| `cli.tui.client` | 394 | — |
| `cli.tui.commands` | 251 | — |
| `cli.tui.keybindings` | 90 | TUI용 키바인딩 설정. |
| `cli.tui.markdown` | 535 | Markdown → Rich 렌더러블, 터미널 트랜스크립트에 맞게 조정됨. |
| `cli.tui.session` | 216 | TUI용 세션 영속화. |
| `cli.tui.sse` | 98 | — |
| `cli.tui.state` | 280 | TUI 사이드바, 활동 피드 및 팔레트를 위한 순수 클라이언트 측 UI 상태. |
| `cli.tui.widgets.call_human` | 85 | 트랜스크립트에 렌더링되는 call_human 알림 카드. |
| `cli.tui.widgets.chat_input` | 152 | — |
| `cli.tui.widgets.palette` | 115 | 슬래시 명령어 완성 팔레트. |
| `cli.tui.widgets.response_status` | 63 | — |
| `cli.tui.widgets.sidebar` | 248 | 사이드바 위젯: anima 목록 + 활동 피드. |
| `cli.tui.widgets.status_bar` | 160 | — |
| `cli.tui.widgets.thinking` | 98 | — |
| `cli.tui.widgets.tool_card` | 140 | — |
| `cli.tui.widgets.transcript` | 291 | — |

## `cli.tui.widgets`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.tui.widgets` | 32 | — |

## `core`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core` | 7 | — |
| `core.credentials` | 276 | — |
| `core.exceptions` | 145 | — |
| `core.internal_api` | 39 | — |
| `core.paths` | 218 | AnimaWorks의 중앙 집중식 경로 해석. |
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
| `core.activity.logger` | 580 | — |
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
| `core.agent.agent_core` | 324 | — |
| `core.agent.cycle` | 1522 | — |
| `core.agent.executor_factory` | 176 | — |
| `core.agent.priming` | 493 | — |
| `core.agent.prompt_log` | 194 | — |
| `core.agent.session_compactor` | 557 | Anima별 × thread_id별 유휴 압축 타이머 관리. |

## `core.anima`

Digital Anima의 라이프사이클과 런타임 객체.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.anima` | 23 | — |
| `core.anima._mixin_protocols（非公開）` | 128 | Structural host protocols for the compositional mixins. |
| `core.anima.asset_reconciler` | 790 | — |
| `core.anima.bootstrap_state` | 576 | — |
| `core.anima.digital_anima` | 685 | — |
| `core.anima.emotion_tag` | 84 | Shared emotion-tag extraction for LLM responses. |
| `core.anima.factory` | 770 | Anima creation factory: create new Digital Animas from templates, blank, or MD files. |
| `core.anima.heartbeat` | 961 | — |
| `core.anima.image_artifacts` | 219 | — |
| `core.anima.inbox` | 989 | — |
| `core.anima.inbox_overflow` | 130 | — |
| `core.anima.lifecycle` | 1405 | — |
| `core.anima.messaging` | 1325 | — |
| `core.anima.response_normalize` | 141 | — |
| `core.anima.roster` | 83 | — |
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

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.config` | 36 | — |
| `core.config.anima_registry` | 313 | config.json의 Anima 등록: 등록, 등록 해제, 이름 변경. |
| `core.config.cli` | 340 | ``animaworks config`` 하위 명령어의 CLI 핸들러. |
| `core.config.env_slots` | 92 | — |
| `core.config.file_access_policy` | 536 | — |
| `core.config.global_permissions` | 251 | — |
| `core.config.io` | 303 | 설정 I/O: 싱글턴 캐시, 로드 및 저장. |
| `core.config.local_llm` | 69 | 로컬 Ollama 기반 모델 기본값 및 역할 프리셋을 위한 헬퍼. |
| `core.config.migrate` | 220 | 레거시 permissions.md 파일을 permissions.json로 마이그레이션. |
| `core.config.model_catalog` | 171 | 정적 모델 카탈로그 및 요청별 모델 오버라이드 검증. |
| `core.config.model_config` | 879 | 모델 설정 해석: load_model_config, penalties, max_tokens. |
| `core.config.model_discovery` | 521 | 설치된 CLI에서 "모드 + 모델" 카탈로그의 동적 탐색. |
| `core.config.model_mode` | 446 | 표준 S/C/D/G/X/A 모드에 대한 모델 실행 모드 해석. |
| `core.config.models` | 94 | 중앙 설정 모듈 — 분할 모듈을 다시 내보내는 퍼사드. |
| `core.config.resolver` | 159 | 설정 해석: status.json와 anima_defaults 병합. |
| `core.config.schemas` | 1330 | AnimaWorks용 Pydantic 설정 스키마. |
| `core.config.vault` | 409 | PyNaCl SealedBox 암호화를 사용한 자격 증명 볼트. |

## `core.execution`

도구 실행, 명령 실행, 안전 제어.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution` | 57 | — |
| `core.execution._shortterm_handoff（非公開）` | 112 | — |
| `core.execution._streaming（非公開）` | 303 | — |
| `core.execution._tool_summary（非公開）` | 99 | — |
| `core.execution.base` | 902 | — |
| `core.execution.busy_probe` | 68 | 자체 호스팅 폴백 모델용 혼잡 프로브 (vLLM ``/metrics``). |
| `core.execution.cli_stream` | 328 | — |
| `core.execution.engine_base` | 76 | — |
| `core.execution.engines.claude._sdk_hooks（非公開）` | 652 | — |
| `core.execution.engines.claude._sdk_interrupt（非公開）` | 106 | — |
| `core.execution.engines.claude._sdk_options（非公開）` | 567 | — |
| `core.execution.engines.claude._sdk_patch（非公開）` | 261 | — |
| `core.execution.engines.claude._sdk_security（非公開）` | 294 | — |
| `core.execution.engines.claude._sdk_session（非公開）` | 510 | — |
| `core.execution.engines.claude._sdk_stream（非公開）` | 496 | — |
| `core.execution.engines.claude.executor` | 836 | — |
| `core.execution.engines.codex.events` | 664 | — |
| `core.execution.engines.codex.executor` | 839 | — |
| `core.execution.engines.codex.setup` | 955 | — |
| `core.execution.engines.cursor.executor` | 664 | — |
| `core.execution.engines.gemini.executor` | 470 | — |
| `core.execution.engines.grok.executor` | 1054 | — |
| `core.execution.engines.litellm._litellm_context（非公開）` | 526 | — |
| `core.execution.engines.litellm._litellm_tools（非公開）` | 404 | — |
| `core.execution.engines.litellm._llm_call（非公開）` | 326 | — |
| `core.execution.engines.litellm.executor` | 1048 | — |
| `core.execution.events` | 255 | — |
| `core.execution.fallback_activity` | 290 | 임시 런타임 모델 폴백을 위한 활동 로그 통합. |
| `core.execution.github_identity` | 162 | 실행자 환경을 위한 GitHub 신원 해석. |
| `core.execution.loop_guards` | 411 | 자체 호스팅 실행 루프용 루프 내 가드 메커니즘 (Mode A/B). |
| `core.execution.process_runner` | 184 | — |
| `core.execution.reminder` | 128 | — |
| `core.execution.session.engine_session` | 101 | — |
| `core.execution.session.session_context` | 114 | — |
| `core.execution.session.session_ids` | 82 | — |
| `core.execution.session.session_store` | 130 | — |
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

번역 카탈로그 및 언어 선택.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.i18n` | 135 | 런타임 문자열을 위한 경량 i18n 지원. |
| `core.i18n.strings.communication` | 46 | 도메인별 i18n 문자열. |
| `core.i18n.strings.company` | 14 | 회사 관리를 위한 지역화된 문자열. |
| `core.i18n.strings.config` | 297 | 도메인별 i18n 문자열. |
| `core.i18n.strings.discord` | 28 | — |
| `core.i18n.strings.execution` | 205 | 도메인별 i18n 문자열. |
| `core.i18n.strings.handler` | 382 | 도메인별 i18n 문자열 (핸들러 파트 1). |
| `core.i18n.strings.handler_ext` | 364 | 도메인별 i18n 문자열 (핸들러 파트 2). |
| `core.i18n.strings.lifecycle` | 104 | 도메인별 i18n 문자열. |
| `core.i18n.strings.memory` | 414 | 도메인별 i18n 문자열. |
| `core.i18n.strings.migrate` | 99 | — |
| `core.i18n.strings.misc` | 426 | 도메인별 i18n 문자열. |
| `core.i18n.strings.misc_routes` | 17 | 도메인별 i18n 문자열 (레거시 라우트 모듈). |
| `core.i18n.strings.room_manager` | 29 | 회의실 관리자를 위한 i18n 문자열. |
| `core.i18n.strings.server` | 241 | 도메인별 i18n 문자열. |
| `core.i18n.strings.supervisor` | 91 | 도메인별 i18n 문자열. |
| `core.i18n.strings.tmp` | 74 | — |
| `core.i18n.strings.tooling` | 121 | 도메인별 i18n 문자열 (도구 프롬프트 및 도구). |
| `core.i18n.strings.tooling_schema` | 476 | 도메인별 i18n 문자열 (schema.*). |
| `core.i18n.strings.tooling_schema_ext` | 132 | 도메인별 i18n 문자열 (schema.* 파트 2). |
| `core.i18n.strings.zoom` | 26 | — |

## `core.i18n.strings`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.i18n.strings` | 61 | 모든 도메인 문자열 모듈을 하나의 딕셔너리로 병합. |

## `core.infra`

로그, 데이터베이스, 캐시 등의 기반 기능.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.infra` | 6 | — |
| `core.infra.auto_updater` | 198 | — |
| `core.infra.event_export` | 389 | — |
| `core.infra.execution_sdk_preflight` | 126 | — |
| `core.infra.gpu` | 173 | — |
| `core.infra.logging_config` | 530 | Centralized logging configuration for AnimaWorks. |
| `core.infra.runtime_init` | 422 | First-launch initialization: copy templates to runtime data directory. |
| `core.infra.startup_progress` | 191 | — |
| `core.infra.tmp_cleanup` | 254 | — |

## `core.integrations`

외부 서비스 연동과 animaworks-tool의 구현.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations` | 369 | AnimaWorks external tools package. |
| `core.integrations._anima_icon_url（非公開）` | 310 | Anima icon URL resolution — dashboard, outbound, Slack, notifications, tools, etc. |
| `core.integrations._async_compat（非公開）` | 41 | Async compatibility helpers for tools with synchronous HTTP clients. |
| `core.integrations._base（非公開）` | 158 | — |
| `core.integrations._cache（非公開）` | 172 | Shared SQLite message cache base class for communication tools. |
| `core.integrations._chatwork_cache（非公開）` | 317 | SQLite message cache for Chatwork offline search and unreplied detection. |
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
| `core.integrations._image_pipeline（非公開）` | 809 | ImageGenPipeline – orchestrates the full character asset generation. |
| `core.integrations._image_schemas（非公開）` | 42 | Tool schemas and CLI guide for image generation. |
| `core.integrations._retry（非公開）` | 170 | Shared retry/backoff utility for AnimaWorks tools. |
| `core.integrations._slack_cache（非公開）` | 430 | SQLite message cache for Slack (offline search, unreplied detection). |
| `core.integrations._slack_client（非公開）` | 308 | Slack Web API client with rate-limit retry and pagination. |
| `core.integrations._slack_cli（非公開）` | 308 | Standalone CLI entry point for Slack tools. |
| `core.integrations._slack_markdown（非公開）` | 240 | Slack markdown conversion and formatting utilities. |
| `core.integrations.aws_collector` | 408 | AnimaWorks AWS collector tool — ECS status, CloudWatch logs & metrics. |
| `core.integrations.call_human` | 404 | — |
| `core.integrations.chatwork` | 281 | Chatwork integration for AnimaWorks. |
| `core.integrations.discord` | 284 | Discord integration for AnimaWorks. |
| `core.integrations.github` | 418 | AnimaWorks GitHub tool — gh CLI wrapper. |
| `core.integrations.gmail` | 1254 | AnimaWorks Gmail tool -- direct Gmail API access. |
| `core.integrations.google_calendar` | 615 | — |
| `core.integrations.google_sheets` | 470 | — |
| `core.integrations.google_tasks` | 445 | AnimaWorks Google Tasks tool -- Google Tasks API access. |
| `core.integrations.image.atlascloud` | 156 | Optional Atlas Cloud backend for character images and reference edits. |
| `core.integrations.image.codex` | 319 | Codex CLI image generation client (image_gen tool via local codex). |
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
| `core.integrations.slack` | 261 | Slack integration for AnimaWorks. |
| `core.integrations.transcribe` | 429 | AnimaWorks transcribe tool -- Whisper speech-to-text with LLM refinement. |
| `core.integrations.web_search` | 408 | Web Search tool for AnimaWorks. |
| `core.integrations.x_search` | 348 | X (Twitter) Search tool for AnimaWorks. |

## `core.integrations.image`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations.image` | 85 | 이미지 및 3D 생성 API 클라이언트와 공통 상수. |

## `core.lifecycle`

Anima의 시작, 종료 및 초기화 라이프사이클.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.lifecycle` | 17 | — |
| `core.lifecycle.knowledge_correction` | 127 | — |
| `core.lifecycle.system_consolidation` | 284 | — |

## `core.llm`

LLM 오류 분류, 레이트 제어, 리트라이의 공통 기능.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.llm` | 1 | LLM-related core utilities. |
| `core.llm.guard.backoff` | 42 | Backoff timing helpers for coordinated LLM retry. |
| `core.llm.guard.error_classifier` | 805 | Centralized LLM API error classification for coordinated recovery. |
| `core.llm.guard.rate_guard` | 341 | Cross-process LLM rate guard (fleet-wide circuit breaker). |
| `core.llm.oneshot` | 879 | Shared LLM helper utilities for memory-management modules. |

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
| `core.mcp.server` | 704 | — |

## `core.memory`

대화·에피소드 기억의 저장, 검색, 정리.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory` | 20 | — |
| `core.memory._llm_parse（非公開）` | 185 | Shared LLM-output parsing helpers for the memory pipeline. |
| `core.memory.config_reader` | 31 | — |
| `core.memory.conversation.compression` | 321 | Compression logic for conversation memory. |
| `core.memory.conversation.finalize` | 477 | Session finalization for conversation memory. |
| `core.memory.conversation.memory` | 327 | Conversation memory (대화 기억 / 워킹 메모리) management. |
| `core.memory.conversation.models` | 149 | Data classes and constants for conversation memory. |
| `core.memory.conversation.prompt` | 270 | Prompt building functions for conversation memory. |
| `core.memory.conversation.shortterm` | 344 | Short-term memory (단기 기억) management. |
| `core.memory.conversation.state_update` | 49 | State update functions for conversation memory finalization. |
| `core.memory.conversation.streaming_journal` | 473 | — |
| `core.memory.facts.config` | 110 | — |
| `core.memory.facts.entity_index` | 452 | — |
| `core.memory.facts.extraction` | 406 | — |
| `core.memory.facts.extractor` | 328 | LLM-based entity and fact extraction pipeline. |
| `core.memory.facts.invalidation` | 497 | — |
| `core.memory.facts.invalidation_llm` | 109 | — |
| `core.memory.facts.observability` | 41 | — |
| `core.memory.facts.ontology` | 231 | Pydantic models for entity / fact extraction results. |
| `core.memory.facts.prompts.en` | 77 | English prompts for entity / fact extraction. |
| `core.memory.facts.prompts.ja` | 78 | Japanese prompts for entity / fact extraction. |
| `core.memory.facts.store` | 460 | — |
| `core.memory.frontmatter` | 430 | — |
| `core.memory.io` | 59 | — |
| `core.memory.maintenance.background_review` | 554 | — |
| `core.memory.maintenance.consolidation` | 926 | — |
| `core.memory.maintenance.cron_logger` | 159 | — |
| `core.memory.maintenance.distillation` | 546 | — |
| `core.memory.maintenance.forgetting` | 588 | — |
| `core.memory.maintenance.housekeeping` | 1471 | — |
| `core.memory.maintenance.hygiene` | 75 | — |
| `core.memory.maintenance.reconsolidation` | 658 | — |
| `core.memory.maintenance.resolution_tracker` | 61 | — |
| `core.memory.manager` | 675 | — |
| `core.memory.peer_profiles` | 37 | — |
| `core.memory.priming.channel_a` | 70 | — |
| `core.memory.priming.channel_b` | 534 | — |
| `core.memory.priming.channel_c` | 618 | — |
| `core.memory.priming.channel_e` | 203 | — |
| `core.memory.priming.channel_f` | 215 | — |
| `core.memory.priming.constants` | 92 | — |
| `core.memory.priming.engine` | 444 | — |
| `core.memory.priming.format` | 119 | — |
| `core.memory.priming.items` | 59 | — |
| `core.memory.priming.outbound` | 142 | — |
| `core.memory.priming.policy` | 25 | — |
| `core.memory.priming.result` | 72 | — |
| `core.memory.priming.utils` | 273 | — |
| `core.memory.rag.cli_access` | 232 | CLI access to phase3 vector stores through the active owner or server. |
| `core.memory.rag.contextual_header` | 163 | — |
| `core.memory.rag.direct_access` | 12 | — |
| `core.memory.rag.embedding` | 396 | — |
| `core.memory.rag.endpoints` | 79 | — |
| `core.memory.rag.episode_time` | 46 | — |
| `core.memory.rag.exclusion` | 38 | — |
| `core.memory.rag.facts_chunker` | 100 | — |
| `core.memory.rag.index_signature` | 27 | Compatibility diagnostics for an existing embedding index signature. |
| `core.memory.rag.indexer` | 1593 | — |
| `core.memory.rag.indexer_delete` | 135 | — |
| `core.memory.rag.owner_lock` | 84 | Exclusive ownership lock for an anima's native vector database. |
| `core.memory.rag.repair.detect` | 743 | — |
| `core.memory.rag.repair.rebuild` | 396 | — |
| `core.memory.rag.repair.service` | 269 | Supervised RAG repair mixin for ProcessSupervisor. |
| `core.memory.rag.repair.state` | 191 | Persistent repair-state helpers for RAG auto-repair. |
| `core.memory.rag.repair.types` | 27 | — |
| `core.memory.rag.retriever` | 809 | — |
| `core.memory.rag.shared_check_registry` | 140 | — |
| `core.memory.rag.shared_meta` | 162 | — |
| `core.memory.rag.sqlite_health` | 359 | — |
| `core.memory.rag.store` | 788 | — |
| `core.memory.rag.vector_client` | 503 | — |
| `core.memory.rag.vector_ops` | 82 | Conversion between vector API requests and the MemoryService wire format. |
| `core.memory.rag.vector_registry` | 160 | — |
| `core.memory.retrieval.bm25` | 1325 | — |
| `core.memory.retrieval.code_index` | 221 | — |
| `core.memory.retrieval.confidence_gate` | 39 | — |
| `core.memory.retrieval.entity` | 192 | — |
| `core.memory.retrieval.pipeline` | 92 | — |
| `core.memory.retrieval.query_expansion` | 496 | — |
| `core.memory.retrieval.rag_search` | 1149 | — |
| `core.memory.retrieval.reranker` | 264 | — |
| `core.memory.retrieval.rrf` | 107 | — |
| `core.memory.retrieval.search_metadata` | 108 | — |
| `core.memory.retrieval.time_expr` | 230 | — |
| `core.memory.retrieval.types` | 38 | — |
| `core.memory.retrieval.unified_search` | 722 | — |
| `core.memory.skill_metadata` | 49 | — |
| `core.memory.state_lock` | 96 | Process-safe locking for ``state/current_state.md`` updates. |

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

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.memory.priming` | 50 | 프라이밍 계층 - 자동 기억 검색(자동 회상). |

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

anima 간 및 외부와의 메시지 배송.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.messaging` | 6 | — |
| `core.messaging.discord_webhooks` | 296 | — |
| `core.messaging.meeting_room_store` | 130 | — |
| `core.messaging.messenger` | 1038 | — |
| `core.messaging.outbound` | 408 | — |
| `core.messaging.outbound_auto` | 377 | — |
| `core.messaging.sender` | 32 | — |

## `core.migrations`

런타임 데이터 형식의 단계적 마이그레이션.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.migrations` | 1 | 런타임 마이그레이션 프레임워크; 특정 모듈을 직접 임포트하세요. |
| `core.migrations.registry` | 149 | — |
| `core.migrations.steps` | 1234 | AnimaWorks 런타임 데이터용 마이그레이션 단계 구현. |
| `core.migrations.template_sync` | 133 | — |
| `core.migrations.tracker` | 143 | — |

## `core.notification`

알림의 생성과 배송.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.notification` | 40 | — |
| `core.notification.channels.chatwork` | 79 | — |
| `core.notification.channels.discord` | 251 | — |
| `core.notification.channels.line` | 86 | — |
| `core.notification.channels.ntfy` | 87 | — |
| `core.notification.channels.slack` | 261 | — |
| `core.notification.channels.telegram` | 91 | — |
| `core.notification.interactive` | 620 | — |
| `core.notification.notifier` | 219 | — |
| `core.notification.reply_routing` | 472 | — |
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
| `core.org.company` | 1217 | Company membership and cross-company boundary helpers. |
| `core.org.company_resources` | 86 | — |
| `core.org.hierarchy` | 39 | — |
| `core.org.org_sync` | 482 | — |
| `core.org.workspace` | 232 | — |

## `core.platform`

실행 엔진이나 OS별 차이를 흡수하는 연계 계층.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.platform` | 4 | — |
| `core.platform.atomic_io` | 172 | — |
| `core.platform.claude_code` | 194 | — |
| `core.platform.codex` | 216 | — |
| `core.platform.cursor` | 60 | — |
| `core.platform.env` | 84 | — |
| `core.platform.fd_limits` | 60 | — |
| `core.platform.gemini` | 42 | — |
| `core.platform.grok` | 40 | — |
| `core.platform.locks` | 125 | — |
| `core.platform.pid` | 32 | — |
| `core.platform.process` | 320 | — |
| `core.platform.processing_lease` | 336 | — |
| `core.platform.status_store` | 51 | — |
| `core.platform.subprocess_entries` | 23 | — |
| `core.platform.tasks` | 35 | — |

## `core.prompt`

시스템 프롬프트와 컨텍스트의 구축.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.prompt` | 1 | Prompt construction package; import specific modules directly. |
| `core.prompt.assembler` | 307 | — |
| `core.prompt.builder` | 1274 | — |
| `core.prompt.context` | 469 | Context window usage tracker. |
| `core.prompt.messaging` | 147 | — |
| `core.prompt.org_context` | 378 | — |
| `core.prompt.sections` | 52 | — |

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

## `core.supervisor`

anima의 감독, 위임, 실행 조정.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.supervisor` | 20 | — |
| `core.supervisor._manager_protocols（非公開）` | 84 | Structural host protocols for the compositional mixins. |
| `core.supervisor._mgr_health（非公開）` | 470 | Health check mixin for ProcessSupervisor. |
| `core.supervisor._mgr_rag_repair（非公開）` | 9 | Supervisor entry point for the RAG repair lifecycle mixin. |
| `core.supervisor._mgr_reconcile（非公開）` | 319 | Reconciliation mixin for ProcessSupervisor. |
| `core.supervisor._mgr_scheduler（非公開）` | 1035 | System scheduler mixin for ProcessSupervisor. |
| `core.supervisor.cron_followup` | 45 | Shared command-cron follow-up policy for legacy and isolated runners. |
| `core.supervisor.event_bus` | 88 | In-process event buffer for events emitted by an anima root runner. |
| `core.supervisor.inbox_rate_limiter` | 270 | Event-driven inbox wakeups and deferred trigger management. |
| `core.supervisor.ipc` | 508 | IPC communication layer using JSON Lines over a platform-specific transport. |
| `core.supervisor.ipc_v2` | 414 | Persistent duplex IPC v2 used between an anima root and task runners. |
| `core.supervisor.manager` | 1104 | Process Supervisor - Manages lifecycle of Anima child processes. |
| `core.supervisor.memory_service` | 770 | Root-owned vector memory service. |
| `core.supervisor.process_handle` | 768 | Process handle for managing child Anima processes. |
| `core.supervisor.restart_state` | 169 | Unified restart state machine for ProcessSupervisor. |
| `core.supervisor.runner` | 1246 | Child process entry point for Anima subprocess. |
| `core.supervisor.schedule_parser` | 484 | — |
| `core.supervisor.scheduler_manager` | 885 | APScheduler management for heartbeat and cron tasks. |
| `core.supervisor.streaming_handler` | 439 | Streaming IPC message handler. |
| `core.supervisor.task_runner` | 960 | Disposable task runner entry point. |
| `core.supervisor.task_runner_supervisor` | 1116 | Root-side lifecycle manager for disposable task runner processes. |
| `core.supervisor.transport` | 240 | Transport helpers for IPC server/client communication. |

## `core.tasks`

작업 등록, 상태 관리, 실행 제어.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks` | 1 | Task queue, task board, delegated/background task execution and external task sources. |
| `core.tasks.background` | 606 | — |
| `core.tasks.board.board_actions` | 237 | — |
| `core.tasks.board.housekeeping` | 185 | — |
| `core.tasks.board.models` | 37 | Pydantic models for the single TaskBoard view (read straight from TaskStore). |
| `core.tasks.board.notices` | 119 | — |
| `core.tasks.board.readiness` | 31 | Read-only boundary between legacy task files and canonical execution. |
| `core.tasks.board.tasks` | 1233 | Durable execution records; the single source of truth for the TaskBoard. |
| `core.tasks.board.view` | 118 | Single TaskBoard view built directly from the canonical TaskStore. |
| `core.tasks.dispatch` | 355 | — |
| `core.tasks.external.collector` | 209 | Multi-source external tasks collector with per-source fault isolation. |
| `core.tasks.external.models` | 47 | Data models for the external tasks snapshot store. |
| `core.tasks.external.sources.chatwork` | 228 | Chatwork external tasks collector (open my-tasks + unreplied To). |
| `core.tasks.external.sources.github` | 182 | GitHub external tasks collector via ``gh`` CLI. |
| `core.tasks.external.sources.gmail` | 124 | Gmail external tasks collector (unread inbox, last 7 days). |
| `core.tasks.external.sources.slack` | 184 | Slack external tasks collector (unreplied mentions via message cache). |
| `core.tasks.external.store` | 51 | Atomic JSON snapshot store for external tasks. |
| `core.tasks.pending_executor` | 1542 | Execute claimed TaskStore work in background lanes. |
| `core.tasks.queue` | 484 | — |
| `core.tasks.wake` | 70 | Cross-process wake fan-out for the PendingTaskExecutor. |

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
| `core.tooling._handler_protocols（非公開）` | 226 | Structural host protocols for the compositional mixins. |
| `core.tooling.codex_command_hook` | 93 | Codex ``PreToolUse`` hook: deny shell commands by the shared command policy. |
| `core.tooling.dispatch` | 252 | — |
| `core.tooling.handler` | 878 | — |
| `core.tooling.handler_base` | 335 | — |
| `core.tooling.handler_comms` | 857 | — |
| `core.tooling.handler_create_anima` | 235 | — |
| `core.tooling.handler_delegation` | 262 | — |
| `core.tooling.handler_exec` | 345 | — |
| `core.tooling.handler_files` | 899 | — |
| `core.tooling.handler_memory` | 1345 | — |
| `core.tooling.handler_org` | 39 | — |
| `core.tooling.handler_org_dashboard` | 203 | — |
| `core.tooling.handler_perms` | 388 | — |
| `core.tooling.handler_skills` | 832 | — |
| `core.tooling.handler_subordinate_control` | 414 | — |
| `core.tooling.handler_workspace` | 256 | — |
| `core.tooling.org_helpers` | 158 | — |
| `core.tooling.permissions` | 330 | — |
| `core.tooling.policy.action_gate` | 188 | — |
| `core.tooling.policy.command_policy` | 455 | — |
| `core.tooling.policy.registry` | 30 | — |
| `core.tooling.policy.schemas.admin` | 221 | — |
| `core.tooling.policy.schemas.builder` | 77 | — |
| `core.tooling.policy.schemas.channel` | 118 | — |
| `core.tooling.policy.schemas.converters` | 27 | — |
| `core.tooling.policy.schemas.loader` | 100 | — |
| `core.tooling.policy.schemas.memory` | 228 | — |
| `core.tooling.policy.schemas.notification` | 67 | — |
| `core.tooling.policy.schemas.session_todo` | 62 | — |
| `core.tooling.policy.schemas.skill` | 306 | — |
| `core.tooling.policy.schemas.supervisor` | 331 | — |
| `core.tooling.policy.schemas.task` | 180 | — |
| `core.tooling.policy.schemas.workspace` | 46 | — |
| `core.tooling.policy.submit_tasks` | 91 | — |
| `core.tooling.policy.surface` | 247 | — |
| `core.tooling.policy.tool_content` | 42 | — |
| `core.tooling.skill_creator` | 120 | — |
| `core.tooling.skill_promotion_tool` | 176 | — |
| `core.tooling.standalone` | 188 | — |
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

LLM 사용량과 비용 기록·집계.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.usage` | 1 | Token usage accounting and per-Anima token budgets. |
| `core.usage.token_budget` | 55 | — |
| `core.usage.token_usage` | 498 | — |

## `core.voice`

음성 입출력과 음성 대화.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.voice` | 7 | Voice chat subsystem — STT, TTS, and session orchestration. |
| `core.voice.front` | 368 | Voice front lane — lightweight speech-first chat path via a local LLM. |
| `core.voice.sentence_splitter` | 73 | Japanese-aware sentence splitting for streaming TTS. |
| `core.voice.session` | 1839 | Voice session — STT -> Chat -> TTS orchestration. |
| `core.voice.stt` | 137 | Voice STT — in-memory PCM transcription via faster-whisper. |
| `core.voice.stt_stream` | 300 | Streaming STT — rolling buffer + LocalAgreement-2 prefix commitment. |
| `core.voice.tts_base` | 61 | TTS abstract base — provider interface and config. |
| `core.voice.tts_elevenlabs` | 133 | ElevenLabs TTS provider — REST API streaming. |
| `core.voice.tts_factory` | 47 | TTS provider factory. |
| `core.voice.tts_gemini` | 183 | Gemini TTS provider — Gemini API Interactions endpoint (SSE streaming). |
| `core.voice.tts_irodori` | 79 | Irodori-TTS provider — HTTP API. |
| `core.voice.tts_sbv2` | 112 | Style-BERT-VITS2 / AivisSpeech TTS provider. |
| `core.voice.tts_voicevox` | 110 | VOICEVOX TTS provider — Engine HTTP API. |

## `server`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server` | 7 | — |
| `server.app` | 1370 | — |
| `server.events` | 56 | — |
| `server.internal_auth` | 232 | — |
| `server.localhost` | 86 | — |
| `server.reload_manager` | 115 | — |
| `server.room_manager` | 541 | Meeting room lifecycle, orchestration, and minutes generation. |
| `server.stream_registry` | 489 | — |
| `server.websocket` | 165 | — |

## `server.gateways`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server.gateways` | 1 | Inbound chat/meeting gateways (Slack, Discord, Zoom, GitHub) run by the server. |
| `server.gateways.discord_channel_sync` | 275 | — |
| `server.gateways.discord_gateway` | 727 | — |
| `server.gateways.github_gateway` | 534 | — |
| `server.gateways.slack_channel_sync` | 493 | — |
| `server.gateways.slack_interactive` | 239 | — |
| `server.gateways.slack_socket` | 1081 | — |
| `server.gateways.zoom_gateway` | 700 | — |

## `server.routes`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server.routes` | 61 | — |
| `server.routes.animas` | 906 | — |
| `server.routes.approve` | 89 | — |
| `server.routes.assets` | 1456 | — |
| `server.routes.auth` | 133 | — |
| `server.routes.channels` | 494 | — |
| `server.routes.chat` | 419 | — |
| `server.routes.chat_chunk_handler` | 289 | — |
| `server.routes.chat_emotion` | 8 | — |
| `server.routes.chat_images` | 80 | — |
| `server.routes.chat_models` | 50 | — |
| `server.routes.chat_producer` | 376 | — |
| `server.routes.chat_resume` | 114 | — |
| `server.routes.chat_ui_state` | 101 | — |
| `server.routes.chat_ws_effects` | 55 | — |
| `server.routes.config_routes` | 329 | — |
| `server.routes.external_tasks` | 261 | — |
| `server.routes.internal` | 1012 | — |
| `server.routes.logs_routes` | 217 | — |
| `server.routes.media_proxy` | 186 | — |
| `server.routes.memory_routes` | 426 | — |
| `server.routes.room` | 443 | Meeting room API routes with SSE streaming. |
| `server.routes.sessions` | 297 | — |
| `server.routes.setup` | 602 | — |
| `server.routes.skills` | 132 | — |
| `server.routes.system` | 1129 | — |
| `server.routes.taskboard` | 235 | — |
| `server.routes.usage_routes` | 844 | — |
| `server.routes.users` | 279 | — |
| `server.routes.voice` | 258 | Voice chat WebSocket endpoint. |
| `server.routes.webhooks` | 503 | — |
| `server.routes.websocket_route` | 46 | — |
