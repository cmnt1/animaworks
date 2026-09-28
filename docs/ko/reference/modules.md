<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/modules.md -->
<!-- i18n: source-sha256=e226d320557a5bc1f409024de315fae5d2d915ff3bf04f688eb4f50bd1273f6c generated=2026-09-28 engine=luna model=gpt-6-luna translator=2 -->

# 모듈 목록

`git ls-files core cli server`에서 추적 대상 Python 파일을 열거합니다. 비공개 모듈에는 표시를 붙였습니다.

## `cli`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli` | 9 | — |
| `cli.__main__（非公開）` | 9 | — |
| `cli._gateway（非公開）` | 112 | — |
| `cli.demo` | 392 | Native ``animaworks demo`` command. |
| `cli.parser` | 1006 | — |

## `cli.commands`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.commands` | 5 | — |
| `cli.commands.anima` | 214 | — |
| `cli.commands.anima_merge` | 72 | — |
| `cli.commands.anima_mgmt` | 1451 | anima 프로세스 관리를 위한 CLI 명령어. |
| `cli.commands.board` | 191 | — |
| `cli.commands.company_cmd` | 226 | — |
| `cli.commands.cost_cmd` | 232 | — |
| `cli.commands.cron_guard` | 93 | cron 가드 작업을 검사하고 다시 활성화하는 CLI 명령어. |
| `cli.commands.import_cmd` | 88 | — |
| `cli.commands.index_cmd` | 426 | — |
| `cli.commands.init_cmd` | 150 | — |
| `cli.commands.internal_cmd` | 362 | — |
| `cli.commands.logs` | 206 | anima 로그를 보기 위한 CLI 명령어. |
| `cli.commands.mcp_cmd` | 66 | — |
| `cli.commands.messaging` | 167 | — |
| `cli.commands.migrate_cmd` | 114 | — |
| `cli.commands.models_cmd` | 219 | 모델 정보 및 관리를 위한 CLI 명령어. |
| `cli.commands.optimize_assets` | 189 | — |
| `cli.commands.profile` | 332 | — |
| `cli.commands.rag_repair_status` | 148 | 지속적 RAG 복구 상태에 대한 상태 보고. |
| `cli.commands.remake_cmd` | 272 | — |
| `cli.commands.repair_rag_cmd` | 135 | — |
| `cli.commands.server` | 975 | — |
| `cli.commands.skills` | 211 | — |
| `cli.commands.supervisor_cmd` | 109 | — |
| `cli.commands.task_cmd` | 568 | — |
| `cli.commands.task_store_cmd` | 118 | 운영자 전용, 코호트 범위의 작업 마이그레이션 및 현재 상태 내보내기. |
| `cli.commands.tmp_cmd` | 173 | — |
| `cli.commands.vault_cmd` | 247 | — |

## `cli.tui`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.tui` | 203 | — |
| `cli.tui.app` | 1817 | — |
| `cli.tui.client` | 394 | — |
| `cli.tui.commands` | 251 | — |
| `cli.tui.keybindings` | 90 | Keybinding configuration for the TUI. |
| `cli.tui.markdown` | 535 | Markdown → Rich renderables, tuned for a terminal transcript. |
| `cli.tui.session` | 213 | Session persistence for the TUI. |
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
| `core.exceptions` | 145 | — |
| `core.internal_api` | 38 | — |
| `core.paths` | 217 | Centralized path resolution for AnimaWorks. |
| `core.schemas` | 240 | — |
| `core.time_utils` | 103 | — |

## `core.agent`

LLM 에이전트 실행, 대화 제어, 엔진 연동.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.agent` | 23 | — |
| `core.agent.agent_core` | 324 | — |
| `core.agent.cycle` | 1598 | — |
| `core.agent.executor_factory` | 178 | — |
| `core.agent.priming` | 465 | — |
| `core.agent.prompt_log` | 194 | — |
| `core.agent.session_compactor` | 557 | Per-Anima × per-thread_id 유휴 압축 타이머 관리. |

## `core.anima`

Digital Anima의 라이프사이클과 런타임 객체.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.anima` | 23 | — |
| `core.anima.asset_reconciler` | 675 | — |
| `core.anima.bootstrap_state` | 575 | — |
| `core.anima.digital_anima` | 674 | — |
| `core.anima.emotion_tag` | 84 | LLM 응답을 위한 공유 감정 태그 추출. |
| `core.anima.factory` | 770 | Anima 생성 팩토리: 템플릿, 빈 파일 또는 MD 파일에서 새 Digital Anima 생성. |
| `core.anima.heartbeat` | 946 | — |
| `core.anima.image_artifacts` | 219 | — |
| `core.anima.inbox` | 1009 | — |
| `core.anima.inbox_overflow` | 130 | — |
| `core.anima.lifecycle` | 1356 | — |
| `core.anima.messaging` | 1608 | — |
| `core.anima.response_normalize` | 141 | — |
| `core.anima.roster` | 83 | — |
| `core.anima.skills_check` | 15 | — |

## `core.auth`

사용자 인증, 세션, 인증 정보 관리.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.auth` | 7 | — |
| `core.auth.manager` | 192 | — |
| `core.auth.models` | 45 | — |

## `core.config`

애플리케이션 설정의 스키마, 로드, 검증, 마이그레이션.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.config` | 42 | — |
| `core.config.anima_registry` | 295 | config.json에서의 Anima 등록: 등록, 등록 해제, 이름 변경. |
| `core.config.cli` | 348 | ``animaworks config`` 하위 명령어에 대한 CLI 핸들러. |
| `core.config.env_slots` | 118 | — |
| `core.config.file_access_policy` | 285 | — |
| `core.config.global_permissions` | 251 | — |
| `core.config.io` | 253 | 구성 I/O: 싱글턴 캐시, 로드 및 저장. |
| `core.config.local_llm` | 100 | 로컬 Ollama 기반 모델 기본값 및 역할 프리셋을 위한 헬퍼. |
| `core.config.migrate` | 944 | 레거시 config.md 파일을 통합 config.json으로 마이그레이션. |
| `core.config.model_catalog` | 171 | 정적 모델 카탈로그 및 요청별 모델 오버라이드 검증. |
| `core.config.model_config` | 860 | 모델 구성 해석: load_model_config, penalties, max_tokens. |
| `core.config.model_discovery` | 521 | 설치된 CLI에서 "모드 + 모델" 카탈로그의 동적 탐색. |
| `core.config.model_mode` | 446 | 표준 S/C/D/G/X/A 모드에 대한 모델 실행 모드 해석. |
| `core.config.models` | 121 | 중앙 구성 모듈 — 분할 모듈을 다시 내보내는 퍼사드. |
| `core.config.resolver` | 172 | 구성 해석: status.json와 anima_defaults 병합. |
| `core.config.schemas` | 1448 | AnimaWorks용 Pydantic 구성 스키마. |
| `core.config.vault` | 473 | PyNaCl SealedBox 암호화를 사용한 자격 증명 볼트. |

## `core.execution`

도구 실행, 명령 실행, 안전 제어.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution` | 60 | — |
| `core.execution._sanitize（非公開）` | 433 | — |
| `core.execution._session（非公開）` | 112 | — |
| `core.execution._streaming（非公開）` | 303 | — |
| `core.execution._tool_summary（非公開）` | 102 | — |
| `core.execution.backoff` | 42 | 조정된 LLM 재시도를 위한 백오프 타이밍 헬퍼. |
| `core.execution.base` | 874 | — |
| `core.execution.cli_stream` | 253 | — |
| `core.execution.engine_base` | 75 | — |
| `core.execution.engine_session` | 101 | — |
| `core.execution.engines.claude._sdk_hooks（非公開）` | 679 | — |
| `core.execution.engines.claude._sdk_interrupt（非公開）` | 106 | — |
| `core.execution.engines.claude._sdk_options（非公開）` | 555 | — |
| `core.execution.engines.claude._sdk_patch（非公開）` | 261 | — |
| `core.execution.engines.claude._sdk_security（非公開）` | 305 | — |
| `core.execution.engines.claude._sdk_session（非公開）` | 524 | — |
| `core.execution.engines.claude._sdk_stream（非公開）` | 461 | — |
| `core.execution.engines.claude.agent_sdk` | 896 | — |
| `core.execution.engines.codex.codex_sdk` | 847 | — |
| `core.execution.engines.codex.events` | 667 | — |
| `core.execution.engines.codex.setup` | 952 | — |
| `core.execution.engines.cursor.cursor_agent` | 711 | — |
| `core.execution.engines.gemini.gemini_cli` | 467 | — |
| `core.execution.engines.grok.grok_cli` | 1087 | — |
| `core.execution.engines.litellm._litellm_context（非公開）` | 524 | — |
| `core.execution.engines.litellm._litellm_streaming（非公開）` | 1398 | — |
| `core.execution.engines.litellm._litellm_tools（非公開）` | 399 | — |
| `core.execution.engines.litellm.litellm_loop` | 617 | — |
| `core.execution.error_classifier` | 805 | 조정된 복구를 위한 중앙 집중식 LLM API 오류 분류. |
| `core.execution.events` | 105 | — |
| `core.execution.fallback_activity` | 290 | 임시 런타임 모델 폴백을 위한 활동 로그 통합. |
| `core.execution.github_identity` | 162 | 실행자 환경을 위한 GitHub ID 해석. |
| `core.execution.loop_guards` | 411 | 자체 호스팅 실행 루프를 위한 루프 내 가드 메커니즘 (모드 A/B). |
| `core.execution.process_runner` | 184 | — |
| `core.execution.rate_guard` | 339 | 프로세스 간 LLM 속도 가드 (플릿 전체 회로 차단기). |
| `core.execution.reminder` | 128 | — |
| `core.execution.session_context` | 109 | — |
| `core.execution.session_store` | 130 | — |
| `core.execution.session_types` | 73 | — |
| `core.execution.tool_evidence` | 182 | — |
| `core.execution.watchdog` | 139 | — |

## `core.execution.engines`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines` | 6 | — |

## `core.execution.engines.claude`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.claude` | 10 | — |

## `core.execution.engines.codex`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.codex` | 6 | — |

## `core.execution.engines.cursor`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.cursor` | 6 | — |

## `core.execution.engines.gemini`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.gemini` | 6 | — |

## `core.execution.engines.grok`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.grok` | 6 | — |

## `core.execution.engines.litellm`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution.engines.litellm` | 6 | — |

## `core.i18n`

번역 카탈로그 및 언어 선택.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.i18n` | 135 | 런타임 문자열을 위한 경량 i18n 지원. |
| `core.i18n.strings.communication` | 52 | 도메인별 i18n 문자열. |
| `core.i18n.strings.company` | 14 | 회사 관리를 위한 지역화된 문자열. |
| `core.i18n.strings.config` | 310 | 도메인별 i18n 문자열. |
| `core.i18n.strings.discord` | 28 | — |
| `core.i18n.strings.execution` | 205 | 도메인별 i18n 문자열. |
| `core.i18n.strings.handler` | 384 | 도메인별 i18n 문자열 (핸들러 파트 1). |
| `core.i18n.strings.handler_ext` | 368 | 도메인별 i18n 문자열 (핸들러 파트 2). |
| `core.i18n.strings.lifecycle` | 104 | 도메인별 i18n 문자열. |
| `core.i18n.strings.memory` | 389 | 도메인별 i18n 문자열. |
| `core.i18n.strings.migrate` | 94 | — |
| `core.i18n.strings.misc` | 434 | 도메인별 i18n 문자열. |
| `core.i18n.strings.misc_routes` | 12 | 도메인별 i18n 문자열 (레거시 라우트 모듈). |
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

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.i18n.strings` | 61 | Merge all domain string modules into a single dict. |

## `core.infra`

로그, 데이터베이스, 캐시 등의 기반 기능.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.infra` | 6 | — |
| `core.infra.auto_updater` | 198 | — |
| `core.infra.event_export` | 379 | — |
| `core.infra.gpu` | 173 | — |
| `core.infra.logging_config` | 530 | Centralized logging configuration for AnimaWorks. |
| `core.infra.runtime_init` | 436 | First-launch initialization: copy templates to runtime data directory. |
| `core.infra.startup_progress` | 191 | — |
| `core.infra.tmp_cleanup` | 254 | — |

## `core.integrations`

외부 서비스 연동과 animaworks-tool의 구현.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations` | 461 | AnimaWorks external tools package. |
| `core.integrations._anima_icon_url（非公開）` | 306 | Anima 아이콘 URL 해석 — 대시보드, 아웃바운드, Slack, 알림, 도구 등. |
| `core.integrations._async_compat（非公開）` | 41 | 동기 HTTP 클라이언트를 사용하는 도구를 위한 비동기 호환 헬퍼. |
| `core.integrations._base（非公開）` | 372 | AnimaWorks 도구의 기본 인프라. |
| `core.integrations._cache（非公開）` | 96 | 커뮤니케이션 도구용 공용 SQLite 메시지 캐시 베이스 클래스. |
| `core.integrations._chatwork_cache（非公開）` | 304 | Chatwork 오프라인 검색 및 미답변 감지를 위한 SQLite 메시지 캐시. |
| `core.integrations._chatwork_client（非公開）` | 240 | Chatwork v2 API용 HTTP 클라이언트. |
| `core.integrations._chatwork_cli（非公開）` | 633 | Chatwork 도구의 독립형 CLI 진입점. |
| `core.integrations._chatwork_identity（非公開）` | 76 | Chatwork 신원 및 위임 해석. |
| `core.integrations._chatwork_markdown（非公開）` | 162 | Markdown을 Chatwork 형식으로 변환하는 유틸리티. |
| `core.integrations._comm_cli（非公開）` | 71 | — |
| `core.integrations._discord_cache（非公開）` | 266 | Discord용 SQLite 메시지 캐시 (오프라인 검색, 동기화 상태). |
| `core.integrations._discord_client（非公開）` | 366 | 속도 제한 재시도를 포함한 Discord REST API v10 클라이언트. |
| `core.integrations._discord_cli（非公開）` | 311 | Discord 도구의 독립형 CLI 진입점. |
| `core.integrations._discord_markdown（非公開）` | 138 | Discord 마크업 헬퍼: 일반 텍스트 정리 및 길이 제한. |
| `core.integrations._image_clients（非公開）` | 93 | image/3D 생성을 위한 API 클라이언트 및 공용 상수. |
| `core.integrations._image_cli（非公開）` | 369 | ``animaworks-tool image_gen``용 CLI 진입점. |
| `core.integrations._image_glb（非公開）` | 473 | GLB/FBX 에셋 변환, 최적화 및 압축. |
| `core.integrations._image_pipeline（非公開）` | 809 | ImageGenPipeline – 전체 캐릭터 에셋 생성을 조율. |
| `core.integrations._image_schemas（非公開）` | 42 | 이미지 생성을 위한 도구 스키마 및 CLI 가이드. |
| `core.integrations._retry（非公開）` | 223 | AnimaWorks 도구용 공용 retry/backoff 유틸리티. |
| `core.integrations._slack_cache（非公開）` | 387 | Slack용 SQLite 메시지 캐시 (오프라인 검색, 미답변 감지). |
| `core.integrations._slack_client（非公開）` | 320 | 속도 제한 재시도 및 페이지네이션을 포함한 Slack Web API 클라이언트. |
| `core.integrations._slack_cli（非公開）` | 320 | Slack 도구의 독립형 CLI 진입점. |
| `core.integrations._slack_markdown（非公開）` | 240 | Slack 마크다운 변환 및 포맷 유틸리티. |
| `core.integrations.aws_collector` | 393 | AnimaWorks AWS 수집 도구 — ECS 상태, CloudWatch 로그 및 메트릭. |
| `core.integrations.call_human` | 402 | — |
| `core.integrations.chatwork` | 192 | AnimaWorks용 Chatwork 통합. |
| `core.integrations.discord` | 276 | AnimaWorks용 Discord 통합. |
| `core.integrations.github` | 400 | AnimaWorks GitHub 도구 — gh CLI 래퍼. |
| `core.integrations.gmail` | 1255 | AnimaWorks Gmail 도구 -- Gmail API 직접 접근. |
| `core.integrations.google_calendar` | 628 | — |
| `core.integrations.google_sheets` | 470 | — |
| `core.integrations.google_tasks` | 455 | AnimaWorks Google Tasks 도구 -- Google Tasks API 접근. |
| `core.integrations.image.atlascloud` | 156 | 캐릭터 이미지 및 참조 편집을 위한 선택적 Atlas Cloud 백엔드. |
| `core.integrations.image.codex` | 319 | Codex CLI 이미지 생성 클라이언트 (로컬 codex를 통한 image_gen 도구). |
| `core.integrations.image.constants` | 57 | image/3D 생성을 위한 URL 상수, 타임아웃 및 실행 프로필. |
| `core.integrations.image.diffusers_local` | 904 | 로컬 Diffusers 기반 이미지 생성 헬퍼. |
| `core.integrations.image.fal` | 243 | Fal.ai Flux Kontext 및 Flux Pro 텍스트-이미지 API 클라이언트. |
| `core.integrations.image.meshy` | 310 | Meshy Image-to-3D, 리깅 및 애니메이션 API 클라이언트. |
| `core.integrations.image.novelai` | 192 | 애니메 전신 이미지 생성을 위한 NovelAI V4.5 API 클라이언트. |
| `core.integrations.image.prompts` | 197 | 버스트업, 치비 및 표정 변형을 위한 프롬프트 상수. |
| `core.integrations.image.utils` | 135 | image/3D 생성 클라이언트용 공용 유틸리티. |
| `core.integrations.image_gen` | 433 | AnimaWorks용 캐릭터 이미지 및 3D 모델 생성 도구. |
| `core.integrations.local_llm` | 542 | AnimaWorks 로컬 LLM 도구 -- Ollama API 클라이언트. |
| `core.integrations.notion` | 825 | AnimaWorks용 Notion 통합. |
| `core.integrations.slack` | 245 | AnimaWorks용 Slack 통합. |
| `core.integrations.transcribe` | 420 | AnimaWorks 전사 도구 -- LLM 정제를 포함한 Whisper 음성-텍스트 변환. |
| `core.integrations.web_search` | 399 | AnimaWorks용 웹 검색 도구. |
| `core.integrations.x_search` | 335 | AnimaWorks용 X (트위터) 검색 도구. |

## `core.integrations.image`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations.image` | 85 | 이미지 및 3D 생성 API 클라이언트와 공용 상수. |

## `core.lifecycle`

anima의 시작, 종료, 초기화 라이프사이클.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.lifecycle` | 18 | — |
| `core.lifecycle.anima_merge.content_refs` | 386 | — |
| `core.lifecycle.anima_merge.credential_refs` | 65 | — |
| `core.lifecycle.anima_merge.external_refs` | 435 | — |
| `core.lifecycle.anima_merge.finalize` | 440 | — |
| `core.lifecycle.anima_merge.journal` | 188 | — |
| `core.lifecycle.anima_merge.service` | 1695 | — |
| `core.lifecycle.anima_merge.task_refs` | 402 | — |
| `core.lifecycle.anima_merge.taskboard_refs` | 162 | — |
| `core.lifecycle.anima_merge.verification` | 268 | — |
| `core.lifecycle.knowledge_correction` | 127 | — |
| `core.lifecycle.system_consolidation` | 279 | — |

## `core.lifecycle.anima_merge`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.lifecycle.anima_merge` | 22 | — |

## `core.mcp`

Model Context Protocol 서버와 클라이언트.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.mcp` | 0 | — |
| `core.mcp.server` | 739 | — |
| `core.mcp.trigger_tools` | 84 | — |

## `core.memory`

대화·에피소드 기억의 저장, 검색, 정리.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory` | 22 | — |
| `core.memory._io（非公開）` | 76 | — |
| `core.memory._llm_parse（非公開）` | 200 | 메모리 파이프라인용 공용 LLM 출력 파싱 헬퍼. |
| `core.memory._llm_utils（非公開）` | 885 | 메모리 관리 모듈용 공용 LLM 헬퍼 유틸리티. |
| `core.memory.activity.audit` | 290 | — |
| `core.memory.activity.conversation` | 492 | — |
| `core.memory.activity.format` | 567 | — |
| `core.memory.activity.logger` | 585 | — |
| `core.memory.activity.models` | 202 | — |
| `core.memory.activity.replay` | 537 | — |
| `core.memory.activity.rotation` | 187 | — |
| `core.memory.activity.timeline` | 348 | — |
| `core.memory.config_reader` | 31 | — |
| `core.memory.conversation.compression` | 321 | 대화 메모리 압축 로직. |
| `core.memory.conversation.finalize` | 477 | 대화 메모리 세션 종료 처리. |
| `core.memory.conversation.memory` | 327 | 대화 메모리(회화 기억 / 워킹 메모리) 관리. |
| `core.memory.conversation.models` | 149 | 대화 메모리용 데이터 클래스 및 상수. |
| `core.memory.conversation.prompt` | 270 | 대화 메모리용 프롬프트 구성 함수. |
| `core.memory.conversation.shortterm` | 349 | 단기 기억 관리. |
| `core.memory.conversation.state_update` | 49 | 대화 메모리 종료 처리를 위한 상태 업데이트 함수. |
| `core.memory.conversation.streaming_journal` | 473 | — |
| `core.memory.facts.config` | 110 | — |
| `core.memory.facts.entity_index` | 452 | — |
| `core.memory.facts.extraction` | 435 | — |
| `core.memory.facts.extractor` | 328 | LLM 기반 개체 및 사실 추출 파이프라인. |
| `core.memory.facts.invalidation` | 497 | — |
| `core.memory.facts.invalidation_llm` | 109 | — |
| `core.memory.facts.observability` | 41 | — |
| `core.memory.facts.ontology` | 241 | 개체 / 사실 추출 결과용 Pydantic 모델. |
| `core.memory.facts.prompts.en` | 77 | 개체 / 사실 추출용 영어 프롬프트. |
| `core.memory.facts.prompts.ja` | 78 | 개체 / 사실 추출용 일본어 프롬프트. |
| `core.memory.facts.store` | 460 | — |
| `core.memory.frontmatter` | 430 | — |
| `core.memory.maintenance.background_review` | 554 | — |
| `core.memory.maintenance.consolidation` | 926 | — |
| `core.memory.maintenance.cron_logger` | 159 | — |
| `core.memory.maintenance.distillation` | 542 | — |
| `core.memory.maintenance.forgetting` | 507 | — |
| `core.memory.maintenance.housekeeping` | 1691 | — |
| `core.memory.maintenance.hygiene` | 75 | — |
| `core.memory.maintenance.reconsolidation` | 657 | — |
| `core.memory.maintenance.resolution_tracker` | 61 | — |
| `core.memory.manager` | 675 | — |
| `core.memory.peer_profiles` | 37 | — |
| `core.memory.priming.channel_a` | 70 | — |
| `core.memory.priming.channel_b` | 534 | — |
| `core.memory.priming.channel_c` | 618 | — |
| `core.memory.priming.channel_e` | 203 | — |
| `core.memory.priming.channel_f` | 215 | — |
| `core.memory.priming.constants` | 92 | — |
| `core.memory.priming.engine` | 666 | — |
| `core.memory.priming.format` | 119 | — |
| `core.memory.priming.items` | 59 | — |
| `core.memory.priming.outbound` | 142 | — |
| `core.memory.priming.policy` | 39 | — |
| `core.memory.priming.result` | 72 | — |
| `core.memory.priming.utils` | 303 | — |
| `core.memory.rag.cli_access` | 231 | 활성 소유자 또는 서버를 통한 phase3 벡터 저장소 CLI 접근. |
| `core.memory.rag.contextual_header` | 163 | — |
| `core.memory.rag.direct_access` | 12 | — |
| `core.memory.rag.embedding` | 396 | — |
| `core.memory.rag.endpoints` | 78 | — |
| `core.memory.rag.entity_graph` | 319 | — |
| `core.memory.rag.episode_time` | 46 | — |
| `core.memory.rag.exclusion` | 38 | — |
| `core.memory.rag.facts_chunker` | 100 | — |
| `core.memory.rag.graph` | 813 | — |
| `core.memory.rag.http_store` | 13 | — |
| `core.memory.rag.index_signature` | 27 | 기존 임베딩 인덱스 시그니처에 대한 호환성 진단. |
| `core.memory.rag.indexer` | 1593 | — |
| `core.memory.rag.indexer_delete` | 135 | — |
| `core.memory.rag.owner_lock` | 84 | anima의 네이티브 벡터 데이터베이스에 대한 단독 소유 잠금. |
| `core.memory.rag.repair` | 33 | — |
| `core.memory.rag.repair_rebuild` | 250 | — |
| `core.memory.rag.repair_service` | 621 | — |
| `core.memory.rag.repair_snapshot` | 152 | 기존 RAG 재구축 경로의 비공개 입력 및 메타데이터 게시. |
| `core.memory.rag.repair_state` | 150 | RAG 자동 복구용 영구 복구 상태 헬퍼. |
| `core.memory.rag.repair_types` | 27 | — |
| `core.memory.rag.repair_utils` | 163 | — |
| `core.memory.rag.retriever` | 1080 | — |
| `core.memory.rag.shared_check_registry` | 140 | — |
| `core.memory.rag.shared_meta` | 162 | — |
| `core.memory.rag.singleton` | 47 | — |
| `core.memory.rag.sqlite_health` | 359 | — |
| `core.memory.rag.store` | 788 | — |
| `core.memory.rag.vector_client` | 491 | — |
| `core.memory.rag.vector_ops` | 82 | 벡터 API 요청과 MemoryService 와이어 형식 간 변환. |
| `core.memory.rag.vector_registry` | 160 | — |
| `core.memory.retrieval.access_boost` | 131 | — |
| `core.memory.retrieval.bm25` | 1325 | — |
| `core.memory.retrieval.code_index` | 221 | — |
| `core.memory.retrieval.confidence_gate` | 39 | — |
| `core.memory.retrieval.entity` | 632 | — |
| `core.memory.retrieval.pipeline` | 109 | — |
| `core.memory.retrieval.query_expansion` | 496 | — |
| `core.memory.retrieval.rag_search` | 1297 | — |
| `core.memory.retrieval.reranker` | 264 | — |
| `core.memory.retrieval.rrf` | 107 | — |
| `core.memory.retrieval.search_metadata` | 108 | — |
| `core.memory.retrieval.temporal` | 196 | — |
| `core.memory.retrieval.time_expr` | 230 | — |
| `core.memory.retrieval.types` | 38 | — |
| `core.memory.retrieval.unified_search` | 895 | — |
| `core.memory.skill_metadata` | 301 | — |
| `core.memory.state_lock` | 96 | ``state/current_state.md`` 업데이트를 위한 프로세스 안전 잠금. |

## `core.memory.activity`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.activity` | 24 | — |

## `core.memory.conversation`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.conversation` | 23 | — |

## `core.memory.facts`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.facts` | 37 | — |

## `core.memory.facts.prompts`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.facts.prompts` | 3 | — |

## `core.memory.maintenance`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.maintenance` | 6 | — |

## `core.memory.priming`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.priming` | 50 | 프라이밍 레이어 - 자동 기억 검색(자동 회상). |

## `core.memory.rag`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.rag` | 30 | — |

## `core.memory.retrieval`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory.retrieval` | 23 | — |

## `core.messaging`

anima 간 및 외부와의 메시지 배달.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.messaging` | 6 | — |
| `core.messaging.cascade_limiter` | 224 | — |
| `core.messaging.discord_webhooks` | 296 | — |
| `core.messaging.meeting_room_store` | 130 | — |
| `core.messaging.messenger` | 1094 | — |
| `core.messaging.outbound` | 406 | — |
| `core.messaging.outbound_auto` | 393 | — |

## `core.migrations`

런타임 데이터 형식의 단계적 마이그레이션.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.migrations` | 21 | — |
| `core.migrations.legacy_flat_skills` | 241 | — |
| `core.migrations.registry` | 149 | — |
| `core.migrations.steps` | 2276 | AnimaWorks 런타임 데이터용 마이그레이션 단계 구현. |
| `core.migrations.template_sync` | 133 | — |
| `core.migrations.tool_prompts` | 194 | — |
| `core.migrations.tracker` | 110 | — |

## `core.notification`

알림 생성 및 배달.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.notification` | 50 | — |
| `core.notification.channels.chatwork` | 87 | — |
| `core.notification.channels.discord` | 240 | — |
| `core.notification.channels.line` | 86 | — |
| `core.notification.channels.ntfy` | 87 | — |
| `core.notification.channels.slack` | 259 | — |
| `core.notification.channels.telegram` | 91 | — |
| `core.notification.interactive` | 684 | — |
| `core.notification.notifier` | 219 | — |
| `core.notification.reply_routing` | 476 | — |
| `core.notification.slack_names` | 67 | — |

## `core.notification.channels`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.notification.channels` | 7 | — |

## `core.org`

회사, 부서, 역할 등의 조직 모델.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.org` | 6 | — |
| `core.org.company` | 1213 | 회사 멤버십 및 회사 간 경계 헬퍼. |
| `core.org.company_resources` | 86 | — |
| `core.org.hierarchy` | 39 | — |
| `core.org.org_sync` | 551 | — |
| `core.org.workspace` | 234 | — |

## `core.platform`

실행 엔진이나 OS별 차이를 흡수하는 연계 계층.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.platform` | 4 | — |
| `core.platform.atomic_io` | 109 | — |
| `core.platform.claude_code` | 194 | — |
| `core.platform.codex` | 214 | — |
| `core.platform.cursor` | 60 | — |
| `core.platform.fd_limits` | 60 | — |
| `core.platform.gemini` | 42 | — |
| `core.platform.grok` | 40 | — |
| `core.platform.locks` | 125 | — |
| `core.platform.process` | 318 | — |
| `core.platform.processing_lease` | 326 | — |

## `core.prompt`

시스템 프롬프트와 컨텍스트 구축.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.prompt` | 8 | — |
| `core.prompt.assembler` | 307 | — |
| `core.prompt.builder` | 1274 | — |
| `core.prompt.context` | 486 | 컨텍스트 창 사용량 추적기. |
| `core.prompt.messaging` | 146 | — |
| `core.prompt.org_context` | 375 | — |
| `core.prompt.sections` | 52 | — |
| `core.prompt.tokens` | 92 | — |
| `core.prompt.tool_content` | 42 | — |

## `core.skills`

스킬의 발견, 로드, 실행 지원.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.skills` | 135 | — |
| `core.skills.activation` | 459 | — |
| `core.skills.activation_render` | 56 | — |
| `core.skills.activation_state` | 89 | — |
| `core.skills.autolearn` | 210 | — |
| `core.skills.autolearn_lifecycle` | 52 | — |
| `core.skills.cron_context` | 251 | — |
| `core.skills.curator` | 606 | — |
| `core.skills.dense` | 226 | — |
| `core.skills.guard` | 430 | — |
| `core.skills.hub` | 551 | — |
| `core.skills.hub_storage` | 63 | — |
| `core.skills.index` | 613 | — |
| `core.skills.ledger` | 404 | — |
| `core.skills.loader` | 176 | — |
| `core.skills.migration._common（非公開）` | 178 | — |
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
| `core.skills.usage` | 222 | — |

## `core.skills.migration`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.skills.migration` | 14 | — |

## `core.skills.sources`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.skills.sources` | 13 | — |

## `core.supervisor`

anima의 감독, 위임, 실행 조정.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.supervisor` | 34 | Process isolation supervisor package. |
| `core.supervisor._mgr_health（非公開）` | 458 | Health check mixin for ProcessSupervisor. |
| `core.supervisor._mgr_rag_repair（非公開）` | 245 | Supervised RAG repair mixin for ProcessSupervisor. |
| `core.supervisor._mgr_reconcile（非公開）` | 316 | Reconciliation mixin for ProcessSupervisor. |
| `core.supervisor._mgr_scheduler（非公開）` | 1059 | System scheduler mixin for ProcessSupervisor. |
| `core.supervisor.cron_followup` | 45 | Shared command-cron follow-up policy for legacy and isolated runners. |
| `core.supervisor.event_bus` | 88 | In-process event buffer for events emitted by an anima root runner. |
| `core.supervisor.inbox_rate_limiter` | 402 | Inbox rate limiting, cascade detection, and deferred trigger management. |
| `core.supervisor.ipc` | 508 | IPC communication layer using JSON Lines over a platform-specific transport. |
| `core.supervisor.ipc_v2` | 414 | Persistent duplex IPC v2 used between an anima root and task runners. |
| `core.supervisor.manager` | 1093 | Process Supervisor - Manages lifecycle of Anima child processes. |
| `core.supervisor.memory_service` | 765 | Root-owned vector memory service. |
| `core.supervisor.process_handle` | 767 | Process handle for managing child Anima processes. |
| `core.supervisor.restart_state` | 169 | Unified restart state machine for ProcessSupervisor. |
| `core.supervisor.runner` | 1248 | Child process entry point for Anima subprocess. |
| `core.supervisor.schedule_parser` | 484 | — |
| `core.supervisor.scheduler_manager` | 1140 | APScheduler management for heartbeat and cron tasks. |
| `core.supervisor.streaming_handler` | 439 | Streaming IPC message handler. |
| `core.supervisor.task_runner` | 952 | Disposable task runner entry point. |
| `core.supervisor.task_runner_supervisor` | 1104 | Root-side lifecycle manager for disposable task runner processes. |
| `core.supervisor.transport` | 236 | Transport helpers for IPC server/client communication. |

## `core.tasks`

작업 등록, 상태 관리, 실행 제어.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks` | 1 | Task queue, task board, delegated/background task execution and external task sources. |
| `core.tasks.background` | 604 | — |
| `core.tasks.board.board_actions` | 237 | — |
| `core.tasks.board.housekeeping` | 185 | — |
| `core.tasks.board.models` | 37 | Pydantic models for the single TaskBoard view (read straight from TaskStore). |
| `core.tasks.board.notices` | 119 | — |
| `core.tasks.board.readiness` | 31 | Read-only boundary between legacy task files and canonical execution. |
| `core.tasks.board.tasks` | 1247 | Durable execution records; the single source of truth for the TaskBoard. |
| `core.tasks.board.view` | 118 | Single TaskBoard view built directly from the canonical TaskStore. |
| `core.tasks.dispatch` | 358 | — |
| `core.tasks.external.collector` | 209 | Multi-source external tasks collector with per-source fault isolation. |
| `core.tasks.external.models` | 47 | Data models for the external tasks snapshot store. |
| `core.tasks.external.sources.chatwork` | 228 | Chatwork external tasks collector (open my-tasks + unreplied To). |
| `core.tasks.external.sources.github` | 182 | GitHub external tasks collector via ``gh`` CLI. |
| `core.tasks.external.sources.gmail` | 124 | Gmail external tasks collector (unread inbox, last 7 days). |
| `core.tasks.external.sources.slack` | 184 | Slack external tasks collector (unreplied mentions via message cache). |
| `core.tasks.external.store` | 51 | Atomic JSON snapshot store for external tasks. |
| `core.tasks.pending_executor` | 1850 | Pending task watcher and executor. |
| `core.tasks.pending_housekeeping` | 49 | — |
| `core.tasks.queue` | 495 | — |
| `core.tasks.wake` | 70 | Cross-process wake fan-out for the PendingTaskExecutor. |

## `core.tasks.board`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks.board` | 11 | TaskBoard: a single view read directly from the canonical TaskStore. |

## `core.tasks.external`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks.external` | 21 | External tasks snapshot store and multi-source collector skeleton. |

## `core.tasks.external.sources`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tasks.external.sources` | 8 | Per-source collectors for external tasks (stubs in this phase). |

## `core.tooling`

도구의 스키마, 권한, 실행 기반.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tooling` | 39 | — |
| `core.tooling.action_gate` | 188 | — |
| `core.tooling.codex_command_hook` | 93 | Codex ``PreToolUse`` hook: deny shell commands by the shared command policy. |
| `core.tooling.command_policy` | 455 | — |
| `core.tooling.dispatch` | 255 | — |
| `core.tooling.handler` | 865 | — |
| `core.tooling.handler_base` | 367 | — |
| `core.tooling.handler_comms` | 902 | — |
| `core.tooling.handler_create_anima` | 237 | — |
| `core.tooling.handler_delegation` | 260 | — |
| `core.tooling.handler_files` | 1220 | — |
| `core.tooling.handler_memory` | 1257 | — |
| `core.tooling.handler_org` | 39 | — |
| `core.tooling.handler_org_dashboard` | 199 | — |
| `core.tooling.handler_perms` | 432 | — |
| `core.tooling.handler_skills` | 879 | — |
| `core.tooling.handler_subordinate_control` | 417 | — |
| `core.tooling.handler_workspace` | 254 | — |
| `core.tooling.org_helpers` | 154 | — |
| `core.tooling.permissions` | 331 | — |
| `core.tooling.schemas.admin` | 238 | — |
| `core.tooling.schemas.builder` | 155 | — |
| `core.tooling.schemas.channel` | 118 | — |
| `core.tooling.schemas.converters` | 27 | — |
| `core.tooling.schemas.loader` | 101 | — |
| `core.tooling.schemas.memory` | 228 | — |
| `core.tooling.schemas.notification` | 67 | — |
| `core.tooling.schemas.session_todo` | 62 | — |
| `core.tooling.schemas.skill` | 306 | — |
| `core.tooling.schemas.supervisor` | 331 | — |
| `core.tooling.schemas.task` | 180 | — |
| `core.tooling.schemas.workspace` | 46 | — |
| `core.tooling.skill_creator` | 120 | — |
| `core.tooling.skill_promotion_tool` | 176 | — |
| `core.tooling.standalone` | 187 | — |

## `core.tooling.schemas`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tooling.schemas` | 79 | Canonical tool schema definitions and format converters. |

## `core.tools`

내부에서 사용하는 도구 구현.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tools` | 58 | — |

## `core.usage`

LLM 사용량과 비용의 기록·집계.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.usage` | 1 | Token usage accounting and per-Anima token budgets. |
| `core.usage.token_budget` | 55 | — |
| `core.usage.token_usage` | 498 | — |

## `core.voice`

음성 입출력과 음성 대화.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.voice` | 7 | Voice chat subsystem — STT, TTS, and session orchestration. |
| `core.voice.front` | 365 | Voice front lane — lightweight speech-first chat path via a local LLM. |
| `core.voice.sentence_splitter` | 73 | Japanese-aware sentence splitting for streaming TTS. |
| `core.voice.session` | 1835 | Voice session — STT -> Chat -> TTS orchestration. |
| `core.voice.stt` | 131 | Voice STT — in-memory PCM transcription via faster-whisper. |
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
| `server.app` | 1412 | — |
| `server.events` | 56 | — |
| `server.internal_auth` | 232 | — |
| `server.localhost` | 86 | — |
| `server.reload_manager` | 115 | — |
| `server.room_manager` | 540 | Meeting room lifecycle, orchestration, and minutes generation. |
| `server.stream_registry` | 489 | — |
| `server.websocket` | 165 | — |

## `server.gateways`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server.gateways` | 1 | Inbound chat/meeting gateways (Slack, Discord, Zoom, GitHub) run by the server. |
| `server.gateways.discord_channel_sync` | 271 | — |
| `server.gateways.discord_gateway` | 731 | — |
| `server.gateways.github_gateway` | 534 | — |
| `server.gateways.slack_channel_sync` | 492 | — |
| `server.gateways.slack_interactive` | 239 | — |
| `server.gateways.slack_socket` | 1081 | — |
| `server.gateways.zoom_gateway` | 700 | — |

## `server.routes`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `server.routes` | 61 | — |
| `server.routes.animas` | 900 | — |
| `server.routes.approve` | 89 | — |
| `server.routes.assets` | 1455 | — |
| `server.routes.auth` | 133 | — |
| `server.routes.channels` | 493 | — |
| `server.routes.chat` | 419 | — |
| `server.routes.chat_chunk_handler` | 288 | — |
| `server.routes.chat_emotion` | 8 | — |
| `server.routes.chat_images` | 80 | — |
| `server.routes.chat_models` | 50 | — |
| `server.routes.chat_producer` | 376 | — |
| `server.routes.chat_resume` | 114 | — |
| `server.routes.chat_ui_state` | 103 | — |
| `server.routes.chat_ws_effects` | 55 | — |
| `server.routes.config_routes` | 520 | — |
| `server.routes.external_tasks` | 261 | — |
| `server.routes.internal` | 1013 | — |
| `server.routes.logs_routes` | 213 | — |
| `server.routes.media_proxy` | 186 | — |
| `server.routes.memory_routes` | 459 | — |
| `server.routes.room` | 443 | Meeting room API routes with SSE streaming. |
| `server.routes.sessions` | 297 | — |
| `server.routes.setup` | 609 | — |
| `server.routes.skills` | 132 | — |
| `server.routes.system` | 1200 | — |
| `server.routes.taskboard` | 235 | — |
| `server.routes.usage_routes` | 847 | — |
| `server.routes.users` | 279 | — |
| `server.routes.voice` | 257 | Voice chat WebSocket endpoint. |
| `server.routes.webhooks` | 502 | — |
| `server.routes.websocket_route` | 46 | — |
