<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/modules.md -->
<!-- i18n: source-sha256=7a7fd10c38325936902a7ce867a67bfc2eba571ed2e65ac728e48c63bb7a4edd generated=2026-10-26 engine=manual model=codex translator=2 -->

# 모듈 목록

`git ls-files core cli server`에서 추적 대상인 Python 파일을 나열합니다. 비공개 모듈에는 표시가 있습니다.

## `cli`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `cli` | 9 | — |
| `cli.__main__（非公開）` | 9 | — |
| `cli._anima_tool（非公開）` | 33 | — |
| `cli._gateway（非公開）` | 93 | — |
| `cli.codex_command_hook` | 64 | Codex의 ``PreToolUse`` 명령 정책 훅을 위한 CLI 어댑터. |
| `cli.demo` | 407 | 네이티브 ``animaworks demo`` 명령. |
| `cli.parser` | 873 | — |
| `cli.tool_dispatch` | 414 | 외부 도구, 태스크 제출, 명령 별칭을 위한 CLI 디스패치. |

## `cli.commands`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `cli.commands` | 5 | — |
| `cli.commands.anima` | 303 | — |
| `cli.commands.anima_mgmt` | 1205 | anima 프로세스 관리를 위한 CLI 명령. |
| `cli.commands.anima_urgent` | 124 | 긴급 모드 태스크 제출을 위한 CLI 명령. |
| `cli.commands.board` | 144 | — |
| `cli.commands.company_cmd` | 272 | — |
| `cli.commands.config_cmd` | 238 | ``animaworks config``을 위한 CLI 핸들러 및 대화형 마법사. |
| `cli.commands.cost_cmd` | 326 | — |
| `cli.commands.enclave_cmd` | 327 | 엔클레이브 런타임을 위한 운영 명령. |
| `cli.commands.import_cmd` | 88 | — |
| `cli.commands.index_cmd` | 380 | — |
| `cli.commands.init_cmd` | 155 | — |
| `cli.commands.internal_cmd` | 156 | — |
| `cli.commands.logs` | 212 | anima 로그 조회를 위한 CLI 명령. |
| `cli.commands.mcp_cmd` | 66 | — |
| `cli.commands.memory_cmd` | 56 | — |
| `cli.commands.messaging` | 86 | — |
| `cli.commands.migrate_cmd` | 114 | — |
| `cli.commands.models_cmd` | 303 | 모델 정보 및 관리를 위한 CLI 명령. |
| `cli.commands.optimize_assets` | 189 | — |
| `cli.commands.profile` | 327 | — |
| `cli.commands.rag_repair_status` | 147 | 영구 RAG 복구 상태에 대한 상태 보고. |
| `cli.commands.remake_cmd` | 272 | — |
| `cli.commands.repair_rag_cmd` | 135 | — |
| `cli.commands.server` | 902 | — |
| `cli.commands.skills` | 211 | — |
| `cli.commands.supervisor_cmd` | 91 | — |
| `cli.commands.task_cmd` | 667 | — |
| `cli.commands.task_store_cmd` | 258 | 운영자 전용, 코호트 범위 태스크 마이그레이션 및 현재 상태 내보내기. |
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
| `cli.tui.keybindings` | 90 | TUI의 키바인딩 구성. |
| `cli.tui.markdown` | 535 | Markdown → Rich 렌더러블, 터미널 트랜스크립트에 맞게 조정됨. |
| `cli.tui.session` | 246 | TUI의 세션 지속성. |
| `cli.tui.sse` | 98 | — |
| `cli.tui.state` | 280 | TUI 사이드바, 활동 피드, 팔레트를 위한 순수 클라이언트 측 UI 상태. |
| `cli.tui.widgets.call_human` | 85 | 트랜스크립트에 렌더링되는 call_human 알림 카드. |
| `cli.tui.widgets.chat_input` | 152 | — |
| `cli.tui.widgets.palette` | 115 | 슬래시 명령 완성 팔레트. |
| `cli.tui.widgets.response_status` | 63 | — |
| `cli.tui.widgets.sidebar` | 248 | 사이드바 위젯: anima 목록 + 활동 피드. |
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
| `core.auth_alert` | 87 | — |
| `core.credentials` | 288 | — |
| `core.exceptions` | 161 | — |
| `core.general_db` | 283 | 공용 범용 데이터베이스 헬퍼. |
| `core.host_api` | 88 | — |
| `core.internal_api` | 51 | — |
| `core.jev_credits` | 273 | 사용량 대시보드를 위한 Jev (TypeSafe System One) 선불 크레딧 회계. |
| `core.paths` | 262 | AnimaWorks를 위한 중앙화된 경로 해석. |
| `core.project_threads` | 212 | — |
| `core.provider_cooldown` | 207 | — |
| `core.schemas` | 246 | — |
| `core.task_closure` | 142 | 태스크 종료 계약 헬퍼. |
| `core.task_granularity` | 138 | — |
| `core.task_request_capture` | 223 | — |
| `core.time_utils` | 103 | — |
| `core.trust` | 436 | — |
| `core.urgent` | 128 | — |

## `core.activity`

활동 로그의 기록, 재생, 타임라인 표시.

| 모듈 | 행 수 | docstring 첫 줄 |
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

LLM 에이전트의 실행, 대화 제어, 엔진 연동.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.agent` | 23 | — |
| `core.agent.agent_core` | 325 | — |
| `core.agent.cycle` | 1801 | — |
| `core.agent.executor_factory` | 176 | — |
| `core.agent.priming` | 516 | — |
| `core.agent.prompt_log` | 151 | — |
| `core.agent.session_compactor` | 566 | Anima별 × thread_id별 유휴 컴팩션 타이머 관리. |

## `core.anima`

Digital Anima의 라이프사이클과 런타임 객체.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.anima` | 23 | — |
| `core.anima._mixin_protocols（非公開）` | 130 | 구성형 믹스인을 위한 구조적 호스트 프로토콜. |
| `core.anima.admin` | 170 | — |
| `core.anima.asset_reconciler` | 764 | — |
| `core.anima.bootstrap_state` | 624 | — |
| `core.anima.digital_anima` | 694 | — |
| `core.anima.emotion_tag` | 84 | LLM 응답을 위한 공용 감정 태그 추출. |
| `core.anima.factory` | 885 | Anima 생성 팩토리: 템플릿, 빈 상태, 또는 MD 파일로부터 새로운 Digital Anima를 생성. |
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

사용자 인증, 세션 및 인증 정보 관리.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.auth` | 7 | — |
| `core.auth.manager` | 192 | — |
| `core.auth.models` | 45 | — |

## `core.channels`

Slack, Discord, Chatwork의 공통 전송 클라이언트와 토큰 해석.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.channels` | 1 | 외부 커뮤니케이션 채널을 위한 공용 클라이언트 및 토큰 해석. |
| `core.channels.chatwork` | 33 | 중앙 Chatwork 메시지 전송 클라이언트. |
| `core.channels.discord` | 393 | 채널 메시징을 위한 중앙 Discord REST API v10 클라이언트. |
| `core.channels.slack` | 97 | 중앙 Slack Web API 및 incoming-webhook 전송 클라이언트. |
| `core.channels.tokens` | 102 | Anima별 외부 채널 토큰 해석. |

## `core.config`

애플리케이션 설정의 스키마, 로드, 검증, 마이그레이션.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.config` | 42 | — |
| `core.config.anima_registry` | 313 | config.json의 Anima 등록: register, unregister, rename. |
| `core.config.antigravity_oauth` | 433 | — |
| `core.config.env_slots` | 92 | — |
| `core.config.file_access_policy` | 585 | — |
| `core.config.global_permissions` | 259 | — |
| `core.config.helper_models` | 498 | — |
| `core.config.io` | 437 | 구성 I/O: 싱글톤 캐시, 로드, 저장. |
| `core.config.jev` | 83 | Jev(TypeSafe System One) API 키와 로컬 지출 원장을 찾습니다. |
| `core.config.local_llm` | 69 | 로컬 Ollama 기반 모델 기본값과 역할 프리셋을 위한 헬퍼. |
| `core.config.migrate` | 208 | — |
| `core.config.model_catalog` | 209 | 정적 모델 카탈로그 및 요청별 모델 재정의 검증. |
| `core.config.model_config` | 893 | 모델 구성 해석: load_model_config, penalties, max_tokens. |
| `core.config.model_discovery` | 647 | 설치된 CLI에서 "모드 + 모델" 카탈로그의 동적 검색. |
| `core.config.model_mode` | 587 | 표준 S/C/D/G/X/A 모드에 대한 모델 실행 모드 해석. |
| `core.config.models` | 103 | 중앙 구성 모듈 — 분할된 모듈을 재내보내는 파사드. |
| `core.config.nanogpt` | 56 | 각 요청마다 로컬 소스에서 nanoGPT 자격 증명을 읽습니다. |
| `core.config.opencode_go` | 79 | — |
| `core.config.ops` | 203 | AnimaWorks 구성 읽기 및 업데이트를 위한 애플리케이션 작업. |
| `core.config.resolver` | 175 | 구성 해석: status.json을 anima_defaults와 병합. |
| `core.config.schemas` | 1621 | AnimaWorks용 Pydantic 구성 스키마. |
| `core.config.vault` | 461 | PyNaCl SealedBox 암호화를 사용하는 자격 증명 보관소. |

## `core.enclave`

격리된 enclave 모드의 설정 모델과 시작 시 보안 가드.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.enclave` | 54 | Enclave 모드: 전용 소켓에 바인드하는 격리된 런타임 인스턴스. |
| `core.enclave.config` | 183 | enclave 모드용 구성 모델. |
| `core.enclave.egress.audit` | 62 | 이그레스 파이프라인에 대한 감사 로깅. |
| `core.enclave.egress.config` | 113 | 이그레스 파이프라인용 구성 모델. |
| `core.enclave.egress.fs` | 38 | enclave file/directory 권한을 강제하는 소규모 파일시스템 헬퍼. |
| `core.enclave.egress.masker.dispatch` | 40 | 내장 마스커의 프로필 디스패치. |
| `core.enclave.egress.masker.facts` | 162 | 레코드 팩트의 규칙 기반 마스킹. |
| `core.enclave.egress.masker.log_pii` | 115 | log/audit PII의 마스킹. |
| `core.enclave.egress.masker.ner` | 99 | MeCab(fugashi + IPADIC)을 사용한 개체명 인식 마스킹. |
| `core.enclave.egress.models` | 57 | 이그레스 파이프라인용 데이터 구조. |
| `core.enclave.egress.pipeline` | 96 | 이그레스 파이프라인: 구성된 단계를 적용하고 오류 발생 시 폐쇄적으로 실패. |
| `core.enclave.egress.stages` | 236 | 이그레스 파이프라인의 단계 구현. |
| `core.enclave.gateway` | 521 | 게이트웨이: enclave 인스턴스의 인그레스 지점. |
| `core.enclave.gateway_server` | 192 | enclave 게이트웨이의 수명 주기 및 Unix 소켓 연결. |
| `core.enclave.guards` | 250 | enclave 모드용 시작 가드. |
| `core.enclave.jobs` | 254 | enclave 게이트웨이용 영구 쿼리 작업. |
| `core.enclave.laravel_crypt` | 115 | Laravel ``Crypt::encryptString`` 페이로드 복호화를 위한 헬퍼. |
| `core.enclave.ops` | 78 | enclave 상태 확인 및 감사 요약을 위한 운영 헬퍼. |
| `core.enclave.raw_store` | 150 | enclave 도구가 읽는 수정되지 않은 결과를 위한 프라이빗 스토리지. |
| `core.enclave.secrets` | 128 | enclave 자격 증명 저장소에서 시크릿을 읽습니다. |
| `core.enclave.ssm_tunnel` | 379 | enclave SQL 소스용 SSM Session Manager 포트 포워드 터널. |

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

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.execution` | 70 | — |
| `core.execution._antigravity_llm（非公開）` | 658 | — |
| `core.execution._model_router（非公開）` | 148 | — |
| `core.execution._rtk_hook_bridge（非公開）` | 107 | 브리지 스크립트: Claude Code CLI Native Hook -> rtk rewrite. |
| `core.execution._shortterm_handoff（非公開）` | 145 | — |
| `core.execution._streaming（非公開）` | 368 | — |
| `core.execution._tool_summary（非公開）` | 103 | — |
| `core.execution.base` | 932 | — |
| `core.execution.busy_probe` | 68 | 자체 호스팅 폴백 모델(vLLM ``/metrics``)용 혼잡 프로브. |
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
| `core.execution.fallback_activity` | 290 | 임시 런타임 모델 폴백을 위한 활동 로그 통합. |
| `core.execution.github_identity` | 162 | 실행기 환경을 위한 GitHub 신원 해석. |
| `core.execution.loop_guards` | 412 | 자체 호스팅 실행 루프(Mode A/B)용 루프 내 가드 메커니즘. |
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
| `core.i18n` | 135 | 런타임 문자열을 위한 경량 i18n 지원. |
| `core.i18n.strings.communication` | 46 | 도메인별 i18n 문자열. |
| `core.i18n.strings.company` | 14 | 회사 관리를 위한 현지화된 문자열. |
| `core.i18n.strings.config` | 856 | 도메인별 i18n 문자열. |
| `core.i18n.strings.discord` | 54 | — |
| `core.i18n.strings.execution` | 254 | 도메인별 i18n 문자열. |
| `core.i18n.strings.handler` | 400 | 도메인별 i18n 문자열(핸들러 파트 1). |
| `core.i18n.strings.handler_ext` | 393 | 도메인별 i18n 문자열(핸들러 파트 2). |
| `core.i18n.strings.lifecycle` | 104 | 도메인별 i18n 문자열. |
| `core.i18n.strings.memory` | 418 | 도메인별 i18n 문자열. |
| `core.i18n.strings.migrate` | 99 | — |
| `core.i18n.strings.misc` | 559 | 도메인별 i18n 문자열. |
| `core.i18n.strings.misc_routes` | 21 | 도메인별 i18n 문자열(레거시 라우트 모듈). |
| `core.i18n.strings.models` | 70 | 모델 검사를 위한 현지화된 CLI 메시지. |
| `core.i18n.strings.phone` | 127 | — |
| `core.i18n.strings.room_manager` | 41 | 회의실 관리자를 위한 i18n 문자열. |
| `core.i18n.strings.server` | 251 | 도메인별 i18n 문자열. |
| `core.i18n.strings.supervisor` | 195 | 도메인별 i18n 문자열. |
| `core.i18n.strings.tmp` | 74 | — |
| `core.i18n.strings.tooling` | 125 | 도메인별 i18n 문자열(도구 프롬프트 및 도구). |
| `core.i18n.strings.tooling_schema` | 512 | 도메인별 i18n 문자열(schema.*). |
| `core.i18n.strings.tooling_schema_ext` | 167 | 도메인별 i18n 문자열(schema.* 파트 2). |
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
| `core.infra.event_export` | 431 | — |
| `core.infra.execution_sdk_preflight` | 128 | — |
| `core.infra.gpu` | 173 | — |
| `core.infra.logging_config` | 650 | AnimaWorks의 중앙 집중식 로깅 구성. |
| `core.infra.runtime_init` | 429 | 최초 실행 초기화: 템플릿을 런타임 데이터 디렉터리에 복사. |
| `core.infra.startup_progress` | 191 | — |
| `core.infra.tmp_cleanup` | 254 | — |

## `core.integrations`

외부 서비스 연동 및 animaworks-tool 구현.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations` | 79 | 핵심 통합 도구 탐색 및 레지스트리. |
| `core.integrations._anima_icon_url（非公開）` | 331 | Anima 아이콘 URL 해석 — 대시보드, 아웃바운드, Slack, 알림, 도구 등. |
| `core.integrations._async_compat（非公開）` | 41 | 동기 HTTP 클라이언트를 사용하는 도구를 위한 비동기 호환 헬퍼. |
| `core.integrations._base（非公開）` | 200 | — |
| `core.integrations._cache（非公開）` | 172 | 커뮤니케이션 도구용 공유 SQLite 메시지 캐시 기본 클래스. |
| `core.integrations._chatwork_cache（非公開）` | 324 | Chatwork 오프라인 검색 및 미답변 감지를 위한 SQLite 메시지 캐시. |
| `core.integrations._chatwork_client（非公開）` | 235 | Chatwork v2 API용 HTTP 클라이언트. |
| `core.integrations._chatwork_cli（非公開）` | 633 | Chatwork 도구의 독립 실행형 CLI 진입점. |
| `core.integrations._chatwork_identity（非公開）` | 76 | Chatwork 아이덴티티 및 위임 해석. |
| `core.integrations._chatwork_markdown（非公開）` | 162 | Markdown-Chatwork 형식 변환 유틸리티. |
| `core.integrations._comm_cli（非公開）` | 64 | — |
| `core.integrations._discord_cache（非公開）` | 293 | Discord용 SQLite 메시지 캐시 (오프라인 검색, 동기화 상태). |
| `core.integrations._discord_client（非公開）` | 47 | 하위 호환 Discord 클라이언트 임포트 경로. |
| `core.integrations._discord_cli（非公開）` | 349 | Discord 도구의 독립 실행형 CLI 진입점. |
| `core.integrations._discord_markdown（非公開）` | 164 | Discord 마크업 헬퍼: 일반 텍스트 정리 및 길이 제한. |
| `core.integrations._google_auth（非公開）` | 175 | Google 통합용 공유 OAuth2 자격 증명 처리. |
| `core.integrations._image_clients（非公開）` | 97 | image/3D 생성용 API 클라이언트 및 공유 상수. |
| `core.integrations._image_cli（非公開）` | 371 | ``animaworks-tool image_gen``의 CLI 진입점. |
| `core.integrations._image_glb（非公開）` | 489 | GLB/FBX 에셋 변환, 최적화 및 압축. |
| `core.integrations._image_pipeline（非公開）` | 815 | ImageGenPipeline – 전체 캐릭터 에셋 생성을 조율. |
| `core.integrations._image_schemas（非公開）` | 42 | 이미지 생성을 위한 도구 스키마 및 CLI 가이드. |
| `core.integrations._retry（非公開）` | 170 | AnimaWorks 도구용 공유 retry/backoff 유틸리티. |
| `core.integrations._slack_cache（非公開）` | 435 | Slack용 SQLite 메시지 캐시 (오프라인 검색, 미답변 감지). |
| `core.integrations._slack_client（非公開）` | 308 | 속도 제한 재시도 및 페이지네이션을 지원하는 Slack Web API 클라이언트. |
| `core.integrations._slack_cli（非公開）` | 308 | Slack 도구의 독립 실행형 CLI 진입점. |
| `core.integrations._slack_markdown（非公開）` | 240 | Slack 마크다운 변환 및 서식 유틸리티. |
| `core.integrations.aws_collector` | 408 | AnimaWorks AWS 수집 도구 — ECS 상태, CloudWatch 로그 및 메트릭. |
| `core.integrations.bluesky` | 365 | AnimaWorks용 Bluesky 검색 도구. |
| `core.integrations.call_human` | 113 | — |
| `core.integrations.chatwork` | 281 | AnimaWorks용 Chatwork 통합. |
| `core.integrations.daily_ops_runner` | 131 | Daily Ops Dashboard 러너 제어 CLI. |
| `core.integrations.discord` | 366 | AnimaWorks용 Discord 통합. |
| `core.integrations.enclave` | 554 | enclave ask 작업 제출 및 관리를 위한 호스트 측 도구. |
| `core.integrations.enclave_aws` | 866 | enclave 런타임용 읽기 전용 AWS 데이터 도구. |
| `core.integrations.enclave_progress` | 111 | anima가 enclave ask 작업에 중간 진행 상황을 기록하는 도구. |
| `core.integrations.enclave_records` | 222 | enclave 런타임 내부에서 구성된 JSONL 데이터셋 읽기. |
| `core.integrations.enclave_sql` | 396 | enclave 런타임용 읽기 전용 MySQL 쿼리 도구. |
| `core.integrations.github` | 418 | AnimaWorks GitHub 도구 — gh CLI 래퍼. |
| `core.integrations.gmail` | 1254 | AnimaWorks Gmail 도구 -- 직접 Gmail API 액세스. |
| `core.integrations.google_calendar` | 615 | — |
| `core.integrations.google_sheets` | 470 | — |
| `core.integrations.google_tasks` | 445 | AnimaWorks Google Tasks 도구 -- Google Tasks API 액세스. |
| `core.integrations.image.atlascloud` | 156 | 캐릭터 이미지 및 참조 편집을 위한 선택적 Atlas Cloud 백엔드. |
| `core.integrations.image.codex` | 327 | Codex CLI 이미지 생성 클라이언트 (로컬 codex를 통한 image_gen 도구). |
| `core.integrations.image.constants` | 57 | image/3D 생성을 위한 URL 상수, 타임아웃 및 실행 프로파일. |
| `core.integrations.image.diffusers_local` | 905 | 로컬 Diffusers 기반 이미지 생성 헬퍼. |
| `core.integrations.image.fal` | 243 | Fal.ai Flux Kontext 및 Flux Pro 텍스트-투-이미지 API 클라이언트. |
| `core.integrations.image.meshy` | 311 | Meshy Image-to-3D, Rigging 및 Animation API 클라이언트. |
| `core.integrations.image.nanogpt` | 154 | 이미지 생성을 위한 NanoGPT API 클라이언트 (텍스트-투-이미지 / 이미지-투-이미지). |
| `core.integrations.image.novelai` | 193 | 애니메이션 전신 이미지 생성을 위한 NovelAI V4.5 API 클라이언트. |
| `core.integrations.image.openai` | 397 | 캐릭터 초상화 생성을 위한 Codex 내장 GPT Image 클라이언트. |
| `core.integrations.image.prompts` | 197 | 버스트업, 치비 및 표정 변형을 위한 프롬프트 상수. |
| `core.integrations.image.utils` | 135 | image/3D 생성 클라이언트용 공유 유틸리티. |
| `core.integrations.image_gen` | 433 | AnimaWorks용 캐릭터 이미지 및 3D 모델 생성 도구. |
| `core.integrations.local_llm` | 552 | AnimaWorks 로컬 LLM 도구 -- Ollama API 클라이언트. |
| `core.integrations.notebooklm` | 627 | AnimaWorks NotebookLM 도구 -- Google NotebookLM 통합. |
| `core.integrations.notion` | 861 | AnimaWorks용 Notion 통합. |
| `core.integrations.property_portal_scraper` | 763 | PROP-07 부동산 매매 포털 모니터. |
| `core.integrations.slack` | 269 | AnimaWorks용 Slack 통합. |
| `core.integrations.transcribe` | 429 | AnimaWorks transcribe 도구 -- LLM 정제를 포함한 Whisper 음성-텍스트 변환. |
| `core.integrations.web_search` | 408 | AnimaWorks용 웹 검색 도구. |
| `core.integrations.x_search` | 348 | AnimaWorks용 X (Twitter) 검색 도구. |

## `core.integrations.image`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.integrations.image` | 90 | 이미지 및 3D 생성 API 클라이언트와 공유 상수. |

## `core.lifecycle`

anima의 시작, 종료, 초기화 라이프사이클.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.lifecycle` | 17 | — |
| `core.lifecycle.knowledge_correction` | 127 | — |
| `core.lifecycle.system_consolidation` | 319 | — |
| `core.lifecycle.system_status` | 313 | — |

## `core.llm`

LLM 오류 분류, 속도 제어, 재시도의 공통 기능.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.llm` | 1 | LLM 관련 핵심 유틸리티. |
| `core.llm.guard.backoff` | 42 | 조정된 LLM 재시도를 위한 백오프 타이밍 헬퍼. |
| `core.llm.guard.error_classifier` | 805 | 조정된 복구를 위한 중앙 집중식 LLM API 오류 분류. |
| `core.llm.guard.rate_guard` | 341 | 프로세스 간 LLM 속도 가드 (플릿 전체 서킷 브레이커). |
| `core.llm.helper_completion` | 145 | — |
| `core.llm.oneshot` | 951 | 메모리 관리 모듈용 공유 LLM 헬퍼 유틸리티. |

## `core.llm.guard`

—

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.llm.guard` | 1 | Provider-independent LLM retry and failure guards. |

## `core.mcp`

Model Context Protocol 서버와 클라이언트.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.mcp` | 0 | — |
| `core.mcp.server` | 728 | — |
| `core.mcp.win_stdin` | 68 | Windows stdin line reader that never leaves a blocking ReadFile pending. |

## `core.memory`

대화·에피소드 기억의 저장, 검색, 정리.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.memory` | 20 | — |
| `core.memory._llm_parse（非公開）` | 185 | Shared LLM-output parsing helpers for the memory pipeline. |
| `core.memory.config_reader` | 31 | — |
| `core.memory.conversation.compression` | 322 | Compression logic for conversation memory. |
| `core.memory.conversation.finalize` | 497 | Session finalization for conversation memory. |
| `core.memory.conversation.memory` | 349 | Conversation memory (会話記憶 / ワーキングメモリ) management. |
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

anima 간 및 외부와의 메시지 전달.

| 모듈 | 행 수 | docstring 첫 줄 |
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

런타임 데이터 형식의 단계적 마이그레이션.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.migrations` | 1 | Runtime migration framework; import specific modules directly. |
| `core.migrations.registry` | 149 | — |
| `core.migrations.steps` | 1212 | Migration step implementations for AnimaWorks runtime data. |
| `core.migrations.template_sync` | 137 | — |
| `core.migrations.tracker` | 143 | — |

## `core.notification`

알림의 생성과 전달.

| 모듈 | 행 수 | docstring 첫 줄 |
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

| 모듈 | 줄 수 | 독스트링 첫 줄 |
|---|---:|---|
| `core.notification.channels` | 7 | — |

## `core.org`

회사, 부서, 역할 등의 조직 모델.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.org` | 6 | — |
| `core.org.company` | 1212 | Company membership and cross-company boundary helpers. |
| `core.org.company_resources` | 86 | — |
| `core.org.hierarchy` | 39 | — |
| `core.org.org_sync` | 483 | — |
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

실행 엔진이나 OS별 차이를 흡수하는 연계 계층.

| 모듈 | 행 수 | docstring 첫 줄 |
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

시스템 프롬프트와 컨텍스트의 구축.

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.prompt` | 1 | Prompt construction package; import specific modules directly. |
| `core.prompt.assembler` | 307 | — |
| `core.prompt.builder` | 1332 | — |
| `core.prompt.context` | 493 | Context window usage tracker. |
| `core.prompt.messaging` | 147 | — |
| `core.prompt.org_context` | 378 | — |
| `core.prompt.sections` | 52 | — |

## `core.reports`

산출물 보고서의 검증, 공개, 리뷰 독촉.

| 모듈 | 행 수 | docstring 1행째 |
|---|---:|---|
| `core.reports` | 1 | Report generation modules managed in the AnimaWorks repository. |
| `core.reports.pending_review_surfacer` | 450 | Surface product drafts that are stuck in 리뷰 대기 back to their reviewer. |
| `core.reports.property._listing_runs（非公開）` | 123 | Listing-run tracking shared by the daily property reports. |
| `core.reports.property.anjo_1k_product_draft` | 1222 | Create the Anjo 1K daily Products draft for Sakura review. |
| `core.reports.property.daily_sale_product_report` | 894 | Create the daily property sale portal Products draft for Sakura review. |
| `core.reports.property.sale_investment_analysis` | 289 | 새로 확인된 매물에 대해 근거와 연결된 예비 투자 보고서를 생성합니다. |
| `core.reports.property.sale_property_registry` | 171 | 포털 및 매매 호가와 무관한 영구 부동산 번호를 관리합니다. |

## `core.reports.property`

—

| 모듈 | 행 수 | docstring 1행째 |
|---|---:|---|
| `core.reports.property` | 1 | Property report generation jobs. |

## `core.runtime`

anima 메인의 런타임 컴포넌트, 프로세스 간 통신, 작업 실행.

| 모듈 | 행 수 | docstring 1행째 |
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

스킬의 발견, 로드, 실행 지원.

| 모듈 | 행 수 | docstring 1행째 |
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

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.skills.migration` | 14 | — |

## `core.skills.sources`

—

| 모듈 | 행 수 | docstring 첫 줄 |
|---|---:|---|
| `core.skills.sources` | 1 | Skill source adapters; import specific modules directly. |

## `core.tasks`

작업의 등록, 상태 관리, 실행 제어.

| 모듈 | 행 수 | docstring 1행째 |
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

| 모듈 | 행 수 | docstring 1행째 |
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

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.tooling.policy` | 1 | Tool schemas and policy primitives shared by execution and tooling. |

## `core.tooling.policy.schemas`

—

| 모듈 | 행 수 | docstring 1행째 |
|---|---:|---|
| `core.tooling.policy.schemas` | 74 | Canonical tool schema definitions and format converters. |

## `core.usage`

LLM 사용량 및 비용 기록·집계.

| 모듈 | 줄 수 | docstring 첫 줄 |
|---|---:|---|
| `core.usage` | 1 | 토큰 사용량 계산 및 Anima별 토큰 예산. |
| `core.usage.token_budget` | 73 | — |
| `core.usage.token_usage` | 605 | — |

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

| 모듈 | 줄 수 | docstring 첫 번째 줄 |
|---|---:|---|
| `server` | 7 | — |
| `server.app` | 1435 | — |
| `server.avatar_upload` | 178 | — |
| `server.enclave_delivery` | 327 | 완료된 enclave ask 작업을 수집하여 호스트 인박스로 전달합니다. |
| `server.events` | 56 | — |
| `server.internal_auth` | 232 | — |
| `server.localhost` | 86 | — |
| `server.project_tasks` | 166 | 회의 설정을 위해 Obsidian Projects DB 작업 메타데이터를 읽습니다. |
| `server.reload_manager` | 115 | — |
| `server.room_manager` | 787 | 회의실 수명 주기, 오케스트레이션 및 회의록 생성. |
| `server.stream_registry` | 489 | — |
| `server.usage_governor` | 1728 | — |
| `server.websocket` | 165 | — |

## `server.gateways`

—

| 모듈 | 줄 수 | docstring 첫 번째 줄 |
|---|---:|---|
| `server.gateways` | 1 | 서버에서 실행되는 인바운드 chat/meeting 게이트웨이(Slack, Discord, Zoom, GitHub). |
| `server.gateways.discord_channel_sync` | 355 | — |
| `server.gateways.discord_debate_threads` | 190 | 토론 스레드: 여러 Anima가 하나의 레코드에 대해 논의하는 Discord 스레드. |
| `server.gateways.discord_gateway` | 1047 | — |
| `server.gateways.github_gateway` | 534 | — |
| `server.gateways.slack_channel_sync` | 505 | — |
| `server.gateways.slack_interactive` | 239 | — |
| `server.gateways.slack_socket` | 1081 | — |
| `server.gateways.zoom_gateway` | 700 | — |

## `server.routes`

—

| 모듈 | 줄 수 | docstring 첫 번째 줄 |
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
| `server.routes.room` | 1082 | SSE 스트리밍을 사용하는 회의실 API 라우트. |
| `server.routes.sessions` | 297 | — |
| `server.routes.setup` | 638 | — |
| `server.routes.skills` | 132 | — |
| `server.routes.sns_search` | 55 | — |
| `server.routes.system` | 1290 | — |
| `server.routes.taskboard` | 237 | — |
| `server.routes.usage_routes` | 1505 | — |
| `server.routes.users` | 280 | — |
| `server.routes.voice` | 223 | 음성 채팅 WebSocket 엔드포인트; Anima별 status.json 설정은 공유 헬퍼를 사용합니다. |
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

| 모듈 | 줄 수 | docstring 첫 번째 줄 |
|---|---:|---|
| `server.supervisor` | 23 | Anima 프로세스 관리를 위한 서버 수준 감독 API. |
| `server.supervisor._manager_protocols（非公開）` | 85 | 구성 믹스인을 위한 구조적 호스트 프로토콜. |
| `server.supervisor._mgr_health（非公開）` | 496 | ProcessSupervisor용 상태 확인 믹스인. |
| `server.supervisor._mgr_rag_repair（非公開）` | 268 | ProcessSupervisor용 감독형 RAG 복구 믹스인. |
| `server.supervisor._mgr_reconcile（非公開）` | 324 | ProcessSupervisor용 조정 믹스인. |
| `server.supervisor._mgr_scheduler（非公開）` | 1511 | ProcessSupervisor용 시스템 스케줄러 믹스인. |
| `server.supervisor.activity_schedule` | 100 | — |
| `server.supervisor.auto_updater` | 198 | — |
| `server.supervisor.manager` | 1328 | 프로세스 감독자 - Anima 자식 프로세스의 수명 주기를 관리합니다. |
| `server.supervisor.process_handle` | 824 | 자식 Anima 프로세스 관리를 위한 프로세스 핸들. |
| `server.supervisor.restart_state` | 169 | ProcessSupervisor용 통합 재시작 상태 머신. |
