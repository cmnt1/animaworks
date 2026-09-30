<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/config.md -->
<!-- i18n: source-sha256=ee2aef29009e2c98144ea857dcfaf50a9d4b32094b89f40c39fbf4ba7a760178 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

# 설정 참조

`AnimaWorksConfig`, per-anima `ModelConfig`, `models.json`의 정의에서 생성하고 있습니다.

## `config.json`

| 키 | 유형 | 기본값 | 설명 |
|---|---|---|---|
| `version` | `int` | `1` | 설정 파일 형식의 버전. |
| `setup_complete` | `bool` | `false` | 초기 설정이 완료되었는지 여부. |
| `locale` | `str` | `"ja"` | 시스템 전체에서 사용하는 기본 언어. |
| `system` | `SystemConfig` | `{SystemConfig}` | 실행 환경, 시간대, 기본 동작에 관한 설정. |
| `system.mode` | `str` | `"server"` | — |
| `system.timezone` | `str` | `""` | IANA TZ 이름; 비어 있으면 시스템에서 자동 감지 |
| `credentials` | `dict[str, CredentialConfig]` | `{"anthropic":{"model":"CredentialConfig"}}` | 외부 모델·서비스의 인증 정보. |
| `credentials.type` | `str` | `"api_key"` | — |
| `credentials.api_key` | `str` | `""` | — |
| `credentials.keys` | `dict[str, str]` | `{}` | — |
| `credentials.base_url` | `str \| None` | `null` | — |
| `model_modes` | `dict[str, str]` | `{}` | 모델 이름 패턴과 실행 모드의 대응. |
| `model_context_windows` | `dict[str, int]` | `{}` | 모델별 컨텍스트 길이의 호환 설정. models.json 사용 권장. |
| `model_max_tokens` | `dict[str, int]` | `{}` | 모델 이름 패턴별 기본 출력 토큰 수. |
| `anima_defaults` | `AnimaDefaults` | `{AnimaDefaults}` | 각 anima에 적용하는 모델·실행 설정의 기본값. |
| `anima_defaults.model` | `str` | `"claude-sonnet-4-6"` | — |
| `anima_defaults.fallback_model` | `str \| None` | `null` | — |
| `anima_defaults.fallback_models` | `list[str]` | `[]` | — |
| `anima_defaults.background_model` | `str \| None` | `null` | — |
| `anima_defaults.background_credential` | `str \| None` | `null` | — |
| `anima_defaults.background_thinking_effort` | `str \| None` | `null` | heartbeat/cron thinking effort 재정의 |
| `anima_defaults.voice_thinking_effort` | `str \| None` | `null` | 음성 채팅 thinking effort 재정의 |
| `anima_defaults.max_tokens` | `int` | `8192` | — |
| `anima_defaults.credential` | `str` | `"anthropic"` | — |
| `anima_defaults.context_threshold` | `float` | `0.5` | — |
| `anima_defaults.context_absolute_ceiling` | `float` | `0.75` | — |
| `anima_defaults.task_compaction_tokens` | `int` | `0` | — |
| `anima_defaults.task_compaction_max` | `int` | `6` | — |
| `anima_defaults.max_session_age_hours` | `float` | `24.0` | — |
| `anima_defaults.conversation_history_threshold` | `float` | `0.3` | — |
| `anima_defaults.execution_mode` | `str \| None` | `null` | None = 모델에서 자동 감지 |
| `anima_defaults.supervisor` | `str \| None` | `null` | — |
| `anima_defaults.speciality` | `str \| None` | `null` | — |
| `anima_defaults.extra_mcp_servers` | `dict[str, dict]` | `{}` | — |
| `anima_defaults.thinking` | `bool \| None` | `null` | 확장 사고 (Bedrock: reasoning_effort, Ollama: think) |
| `anima_defaults.thinking_effort` | `str \| None` | `null` | "low"/"medium"/"high"/"max" (기본값: "high") |
| `anima_defaults.mode_s_auth` | `str \| None` | `null` | Mode S 인증: "max"\|"api"\|"bedrock"\|"vertex"\|None(=max) |
| `anima_defaults.default_workspace` | `str` | `""` | — |
| `anima_defaults.consolidation_enabled` | `bool` | `true` | — |
| `anima_defaults.heartbeat_enabled` | `bool` | `true` | 기본 true. false로 정기 heartbeat만 비활성화. 메시지 기인 HB·cron은 영향 없음 |
| `anima_defaults.token_budget_monthly` | `int \| None` | `null` | None = 월간 토큰 사용량 무제한 |
| `animas` | `dict[str, AnimaModelConfig]` | `{}` | anima별 모델 설정 덮어쓰기. |
| `animas.supervisor` | `str \| None` | `null` | — |
| `animas.company` | `str \| None` | `null` | — |
| `animas.speciality` | `str \| None` | `null` | — |
| `animas.model` | `str \| None` | `null` | — |
| `animas.heartbeat_enabled` | `bool \| None` | `null` | — |
| `animas.background_review_enabled` | `bool \| None` | `null` | — |
| `animas.token_budget_monthly` | `int \| None` | `null` | — |
| `animas.aliases` | `list[str]` | `[]` | — |
| `consolidation` | `ConsolidationConfig` | `{ConsolidationConfig}` | 기억 통합의 동작과 일정. |
| `consolidation.daily_enabled` | `bool` | `true` | — |
| `consolidation.weekly_distillation_enabled` | `bool` | `true` | — |
| `consolidation.synaptic_downscaling_enabled` | `bool` | `true` | — |
| `consolidation.skill_autolearn_enabled` | `bool` | `true` | — |
| `consolidation.curator_auto_apply_enabled` | `bool` | `false` | — |
| `consolidation.daily_time` | `str` | `"02:00"` | 형식: HH:MM |
| `consolidation.min_episodes_threshold` | `int` | `1` | — |
| `consolidation.llm_model` | `str` | `"claude-sonnet-4-6"` | — |
| `consolidation.llm_credential` | `str` | `""` | — |
| `consolidation.episode_summary_max_input_bytes` | `int` | `204800` | 각 일일 에피소드 요약 LLM 호출의 최대 UTF-8 프롬프트 크기. |
| `consolidation.episode_summary_backfill_days` | `int` | `7` | 처리되지 않은 일일 에피소드 활동을 찾기 위해 이만큼의 로컬 일수를 되돌아봄. |
| `consolidation.episode_summary_backfill_max_days_per_run` | `int` | `3` | 한 번의 일일 통합 중 백필할 최대 이전 일수 (어제는 별도). |
| `consolidation.ipc_timeout_base_seconds` | `int` | `1800` | — |
| `consolidation.ipc_timeout_per_activity_entry_seconds` | `float` | `4.0` | — |
| `consolidation.ipc_timeout_per_episode_seconds` | `float` | `120.0` | — |
| `consolidation.ipc_timeout_max_seconds` | `int` | `7200` | — |
| `consolidation.weekly_ipc_timeout_seconds` | `int` | `3600` | — |
| `consolidation.weekly_enabled` | `bool` | `false` | — |
| `consolidation.weekly_time` | `str` | `"sun:03:00"` | 형식: day:HH:MM |
| `consolidation.indexing_enabled` | `bool` | `true` | 일일 RAG 인덱싱 토글 |
| `consolidation.indexing_time` | `str` | `"04:00"` | 형식: HH:MM |
| `consolidation.knowledge_self_correction_enabled` | `bool` | `true` | — |
| `consolidation.knowledge_self_correction_max_reconsolidation_files` | `int` | `5` | — |
| `consolidation.knowledge_self_correction_timeout_seconds` | `int` | `300` | — |
| `consolidation.post_processing_cooldown_seconds` | `int` | `30` | — |
| `consolidation.inactivity_skip_enabled` | `bool` | `true` | — |
| `consolidation.inactivity_days` | `int` | `7` | — |
| `background_review` | `BackgroundReviewConfig` | `{BackgroundReviewConfig}` | 세션 후 비동기 회고와 인물상 업데이트 설정. |
| `background_review.enabled` | `bool` | `true` | — |
| `background_review.chat_every_user_turns` | `int` | `10` | — |
| `background_review.min_interval_minutes` | `int` | `10` | — |
| `background_review.max_per_day` | `int` | `24` | — |
| `background_review.max_input_bytes` | `int` | `61440` | — |
| `background_review.max_writes` | `int` | `3` | — |
| `background_review.peer_profile_max_chars` | `int` | `1500` | — |
| `rag` | `RAGConfig` | `{RAGConfig}` | 검색 확장 생성과 기억 검색 설정. |
| `rag.enabled` | `bool` | `true` | — |
| `rag.embedding_model` | `str` | `"intfloat/multilingual-e5-small"` | — |
| `rag.embedding_e5_prefix_enabled` | `bool` | `false` | 활성화하면 쿼리 임베딩에 embedding_query_prefix를, 인덱싱된 문서 임베딩에 embedding_document_prefix를 접두사로 붙입니다. E5 계열 절제 실험을 위한 것이며, 문서 접두사 변경이 적용되려면 재인덱싱이 필요합니다. |
| `rag.embedding_query_prefix` | `str` | `"query: "` | — |
| `rag.embedding_document_prefix` | `str` | `"passage: "` | — |
| `rag.embedding_max_seq_length` | `int` | `2048` | 임베딩 모델의 최대 시퀀스 길이(토큰) 상한. ruri-v3 같은 장문 컨텍스트 모델은 기본 8192로, 대량 인코딩 중 GPU 활성 메모리를 크게 사용합니다. 0 = 모델 기본값 사용. |
| `rag.use_gpu` | `bool` | `false` | — |
| `rag.min_retrieval_score` | `float` | `0.3` | — |
| `rag.skill_match_min_score` | `float` | `0.75` | — |
| `rag.repair_enabled` | `bool` | `true` | — |
| `rag.repair_error_threshold` | `int` | `2` | — |
| `rag.repair_window_minutes` | `int` | `5` | — |
| `rag.repair_cooldown_minutes` | `int` | `60` | — |
| `rag.repair_max_consecutive_failures` | `int` | `2` | — |
| `rag.repair_timeout_seconds` | `int` | `1800` | — |
| `rag.repair_poll_interval_seconds` | `int` | `5` | — |
| `rag.repair_max_concurrent` | `int` | `1` | — |
| `rag.upsert_quarantine_failure_threshold` | `int` | `3` | — |
| `rag.shared_check_ttl_seconds` | `float` | `30.0` | — |
| `rag.shared_check_backoff_initial_seconds` | `float` | `5.0` | — |
| `rag.shared_check_backoff_max_seconds` | `float` | `300.0` | — |
| `rag.rerank_enabled` | `bool` | `true` | — |
| `rag.rerank_candidate_pool` | `int` | `50` | — |
| `rag.cross_encoder_model` | `str` | `"cross-encoder/ms-marco-MiniLM-L-12-v2"` | — |
| `rag.confidence_threshold` | `float` | `0.35` | — |
| `rag.rrf_confidence_threshold` | `float` | `0.02` | — |
| `rag.facts_extraction_enabled` | `bool` | `true` | — |
| `rag.fact_extraction_timeout_seconds` | `int` | `120` | 레거시 원자적 사실 추출에 사용되는 LLM 호출의 기본 제한 시간(초); Anima별 status.json extraction_timeout이 이 값을 덮어씁니다. |
| `rag.facts_reconcile_enabled` | `bool` | `true` | 추가 전 레거시 원자적 사실 조정 활성화; 실패 시 ADD로 폴백. |
| `rag.facts_reconcile_similarity_threshold` | `float` | `0.82` | 엄격한 LLM duplicate/contradiction/complement 라벨링 전 최소 사실 벡터 유사도. |
| `rag.facts_reconcile_top_k` | `int` | `5` | 레거시 사실 조정 중 고려되는 최대 유사 활성 사실 수. |
| `rag.entity_registry_enabled` | `bool` | `true` | — |
| `gpu` | `GPUConfig` | `{GPUConfig}` | GPU 사용과 장치 선택 설정. |
| `gpu.embedding_device` | `Literal['auto', 'cuda', 'cpu']` | `"auto"` | — |
| `gpu.reranker_device` | `Literal['auto', 'cuda', 'cpu']` | `"cpu"` | — |
| `gpu.embedding_batch_size` | `int` | `32` | — |
| `gpu.embedding_bulk_yield_batches` | `int` | `5` | 대량 작업이 대기 중인 대화형 작업에 양보할 수 있는 최대 연속 임베딩 배치 수. |
| `memory` | `MemoryConfig` | `{MemoryConfig}` | 기억 저장·검색의 공통 설정. |
| `memory.fact_edge_types` | `list[FactEdgeTypeConfig]` | `[]` | — |
| `memory.fact_edge_types.name` | `str` | `"—"` | 대문자 스네이크 케이스 의미적 엣지 유형 이름 |
| `memory.fact_edge_types.description` | `str` | `"—"` | 추출 프롬프트에 표시되는 짧은 설명 |
| `skills` | `SkillsConfig` | `{SkillsConfig}` | 스킬 로드와 관리 설정. |
| `skills.promotion` | `SkillPromotionConfig` | `{SkillPromotionConfig}` | — |
| `skills.promotion.success_count_threshold` | `int` | `3` | — |
| `skills.promotion.confidence_threshold` | `float` | `0.8` | — |
| `skills.promotion.failure_count_max` | `int` | `1` | — |
| `skills.promotion.last_used_within_days` | `int` | `180` | — |
| `skills.cron` | `SkillCronConfig` | `{SkillCronConfig}` | — |
| `skills.cron.max_skill_chars` | `int` | `6000` | — |
| `skills.cron.max_total_chars` | `int` | `12000` | — |
| `skills.cron.allow_warn_caution` | `bool` | `false` | — |
| `skills.cron.allow_destructive` | `bool` | `false` | — |
| `skills.cron.allow_external_send` | `bool` | `false` | — |
| `skills.external_roots` | `list[ExternalSkillRoot]` | `…` | — |
| `skills.external_roots.path` | `str` | `"—"` | ``~``을 포함할 수 있음; 사용 전에 확장됨 |
| `skills.external_roots.engine` | `str` | `"—"` | ^[a-z][a-z0-9-]*$ 패턴 일치 |
| `skills.external_roots.trust_level` | `str` | `"trusted"` | — |
| `skills.external_roots.enabled` | `bool` | `true` | — |
| `chatwork_tool` | `ChatworkToolConfig` | `{ChatworkToolConfig}` | Chatwork 도구의 권한 설정. |
| `chatwork_tool.grants` | `dict[str, dict[str, str]]` | `{}` | — |
| `prompt` | `PromptConfig` | `{PromptConfig}` | 시스템 프롬프트와 프롬프트 구축 설정. |
| `prompt.injection_size_warning_chars` | `int` | `2000` | — |
| `prompt.identity_business_exclude_headings` | `list[str]` | `["外見","基本プロフィール","Appearance","Basic Profile"]` | — |
| `prompt.system_prompt_target_tokens` | `int` | `6000` | — |
| `prompt.system_prompt_ceiling_pct` | `float` | `0.35` | — |
| `prompt.skill_catalog_router_enabled` | `bool` | `true` | — |
| `prompt.skill_catalog_router_top_k` | `int` | `5` | — |
| `prompt.skill_catalog_router_min_score` | `float` | `1.15` | — |
| `prompt.skill_catalog_router_include_body` | `bool` | `true` | — |
| `prompt.skill_catalog_router_dense_enabled` | `bool` | `true` | — |
| `prompt.skill_catalog_router_dense_weight` | `float` | `8.0` | — |
| `prompt.skill_catalog_max_items` | `int` | `3` | — |
| `priming` | `PrimingConfig` | `{PrimingConfig}` | anima 시작 시 로드할 정보 설정. |
| `priming.max_tokens` | `int` | `2000` | — |
| `priming.channel_timeout_seconds` | `float` | `60.0` | — |
| `priming.compact_background_recall_enabled` | `bool` | `true` | — |
| `priming.compact_background_recall` | `CompactBackgroundRecallConfig` | `{CompactBackgroundRecallConfig}` | — |
| `priming.compact_background_recall.related_knowledge_max_items` | `int` | `3` | — |
| `priming.compact_background_recall.related_knowledge_max_tokens` | `int` | `180` | — |
| `priming.compact_background_recall.episodes_max_items` | `int` | `2` | — |
| `priming.compact_background_recall.episodes_max_tokens` | `int` | `400` | — |
| `priming.compact_background_recall.recent_activity_max_items` | `int` | `5` | — |
| `priming.compact_background_recall.recent_activity_max_tokens` | `int` | `300` | — |
| `image_gen` | `ImageGenConfig` | `{ImageGenConfig}` | 이미지 생성 제공자와 기본 파라미터. |
| `image_gen.backend` | `Literal['api', 'diffusers', 'atlascloud']` | `"api"` | — |
| `image_gen.image_style` | `Literal['anime', 'realistic']` | `"realistic"` | — |
| `image_gen.prefer_codex` | `bool` | `true` | codex CLI가 있으면 이미지 생성에 최우선으로 사용 |
| `image_gen.style_reference` | `str \| None` | `null` | 조직 전체 스타일 참조 이미지 경로 |
| `image_gen.style_prefix` | `str` | `""` | 캐릭터 프롬프트 앞에 추가되는 공통 스타일 태그 |
| `image_gen.style_suffix` | `str` | `""` | 캐릭터 프롬프트 뒤에 추가되는 공통 스타일 태그 |
| `image_gen.negative_prompt_extra` | `str` | `""` | 네거티브 프롬프트에 추가되는 추가 태그 |
| `image_gen.vibe_strength` | `float` | `0.6` | Vibe Transfer 강도 (0.0-1.0) |
| `image_gen.vibe_info_extracted` | `float` | `0.8` | Vibe Transfer 정보 추출 (0.0-1.0) |
| `image_gen.enable_3d` | `bool` | `true` | 3D 모델 생성 활성화 (Meshy API) |
| `image_gen.diffusers_text2img_model` | `str` | `"auto"` | — |
| `image_gen.diffusers_img2img_model` | `str` | `"auto"` | — |
| `image_gen.diffusers_text2img_model_realistic` | `str` | `""` | 사실적인 스타일 재정의 |
| `image_gen.diffusers_text2img_model_anime` | `str` | `""` | 애니메 스타일 재정의 |
| `image_gen.diffusers_device` | `Literal['auto', 'cuda', 'cpu']` | `"auto"` | — |
| `image_gen.diffusers_torch_dtype` | `Literal['auto', 'float16', 'float32', 'bfloat16']` | `"auto"` | — |
| `image_gen.diffusers_local_files_only` | `bool` | `true` | — |
| `image_gen.diffusers_num_inference_steps` | `int` | `28` | — |
| `image_gen.diffusers_img2img_strength` | `float` | `0.55` | — |
| `image_gen.ip_adapter_model` | `str` | `"h94/IP-Adapter"` | — |
| `image_gen.ip_adapter_scale` | `float` | `0.6` | IP-Adapter 얼굴 참조 블렌드 가중치 (0.0-1.0) |
| `human_notification` | `HumanNotificationConfig` | `{HumanNotificationConfig}` | 인간에게의 알림 방법과 알림 대상. |
| `human_notification.enabled` | `bool` | `false` | — |
| `human_notification.channels` | `list[NotificationChannelConfig]` | `[]` | — |
| `human_notification.channels.type` | `str` | `"—"` | "slack", "line", "telegram", "chatwork", "ntfy" |
| `human_notification.channels.enabled` | `bool` | `true` | — |
| `human_notification.channels.config` | `dict[str, Any]` | `{}` | — |
| `interaction` | `InteractionConfig` | `{InteractionConfig}` | anima 간 대화와 메시지 처리. |
| `interaction.default_approver_ids` | `list[str]` | `[]` | 기본 Slack 사용자 ID가 호출별 call_human allowed_users와 병합됨. |
| `interaction.web_base_url` | `str` | `""` | — |
| `server` | `ServerConfig` | `{ServerConfig}` | HTTP 서버, 인증, 사용량 제어 설정. |
| `server.session_ttl_days` | `int \| None` | `90` | None = 무제한 |
| `server.ipc_stream_timeout` | `int` | `60` | 청크당 제한 시간(초) |
| `server.keepalive_interval` | `int` | `30` | keep-alive 전송 간격(초) |
| `server.runner_liveness_timeout` | `int` | `900` | — |
| `server.anima_startup_ready_timeout` | `int` | `120` | — |
| `server.anima_stop_timeout` | `float` | `60.0` | — |
| `server.health_check_warmup_seconds` | `int` | `300` | — |
| `server.runner_warmup_seconds` | `int` | `180` | — |
| `server.spawn_timeout` | `int` | `300` | — |
| `server.supervisor_respawn_max_retries` | `int` | `3` | — |
| `server.supervisor_respawn_retry_interval_seconds` | `float` | `30.0` | 기본 백오프 간격(초) |
| `server.supervisor_respawn_backoff_max_seconds` | `float` | `1800.0` | 최대 백오프(초) |
| `server.stream_checkpoint_enabled` | `bool` | `true` | 스트리밍 중 도구 결과 저장 |
| `server.stream_retry_max` | `int` | `3` | 스트림 연결 끊김 시 최대 자동 재시도 횟수 |
| `server.stream_retry_delay_s` | `float` | `5.0` | 재시도 간 지연(초) |
| `server.llm_num_retries` | `int` | `3` | LLM API 호출 재시도 횟수 (429/5xx/network) |
| `server.ollama_keep_alive` | `str` | `""` | — |
| `server.ollama_total_timeout` | `int` | `0` | 단일 Ollama 생성 호출의 하드 상한(초); 0 = 무제한 |
| `server.media_proxy` | `MediaProxyConfig` | `{MediaProxyConfig}` | — |
| `server.media_proxy.mode` | `Literal['allowlist', 'open_with_scan']` | `"open_with_scan"` | — |
| `server.media_proxy.allowed_domains` | `list[str]` | `["cdn.search.brave.com","images.unsplash.com","images.pexels.com","upload.wikimedia.org"]` | — |
| `server.media_proxy.max_bytes` | `int` | `5242880` | — |
| `server.media_proxy.max_redirects` | `int` | `3` | — |
| `server.media_proxy.timeout_connect_s` | `float` | `5.0` | — |
| `server.media_proxy.timeout_read_s` | `float` | `10.0` | — |
| `server.media_proxy.rate_limit_requests` | `int` | `30` | — |
| `server.media_proxy.rate_limit_window_s` | `int` | `60` | — |
| `server.base_path` | `str` | `""` | 리버스 프록시 하위 경로 (예: "/app"); 비어 있으면 루트 배포 |
| `server.internal_api_auth` | `Literal['off', 'log', 'enforce']` | `"log"` | /api/internal/* 호출자 검증 |
| `llm_rate_guard` | `LlmRateGuardConfig` | `{LlmRateGuardConfig}` | LLM 호출 빈도와 동시 실행 수 제어. |
| `llm_rate_guard.enabled` | `bool` | `true` | — |
| `llm_rate_guard.default_block_seconds` | `int` | `60` | — |
| `llm_rate_guard.max_block_seconds` | `int` | `600` | — |
| `llm_rate_guard.quota_block_seconds` | `int` | `1800` | — |
| `llm_rate_guard.max_quota_block_seconds` | `int` | `14400` | — |
| `mcp` | `MCPConfig` | `{MCPConfig}` | MCP 서버 연결과 도구 공개 설정. |
| `mcp.trigger_scoped_tools` | `bool` | `true` | — |
| `external_messaging` | `ExternalMessagingConfig` | `{ExternalMessagingConfig}` | Slack 등 외부 메시징 연동. |
| `external_messaging.preferred_channel` | `str` | `"slack"` | "slack" \| "chatwork" \| "discord" |
| `external_messaging.user_aliases` | `dict[str, UserAliasConfig]` | `{}` | 별칭 → 연락처 정보 |
| `external_messaging.user_aliases.slack_user_id` | `str` | `""` | — |
| `external_messaging.user_aliases.chatwork_room_id` | `str` | `""` | — |
| `external_messaging.user_aliases.discord_user_id` | `str` | `""` | — |
| `external_messaging.user_aliases.outbound_dm` | `bool` | `false` | — |
| `external_messaging.chat_dm_redirect` | `bool` | `false` | — |
| `external_messaging.slack` | `ExternalMessagingChannelConfig` | `{ExternalMessagingChannelConfig}` | — |
| `external_messaging.slack.enabled` | `bool` | `false` | — |
| `external_messaging.slack.mode` | `str` | `"socket"` | "socket" \| "webhook" |
| `external_messaging.slack.anima_mapping` | `dict[str, str]` | `{}` | channel_id → anima_name ("" = 이 채널 무시) |
| `external_messaging.slack.default_anima` | `str` | `""` | 매핑되지 않은 채널의 폴백 anima |
| `external_messaging.slack.app_id_mapping` | `dict[str, str]` | `{}` | api_app_id → anima_name (Anima별 웹훅 라우팅) |
| `external_messaging.slack.auto_response` | `bool` | `false` | LLM 응답을 원래 플랫폼으로 자동 게시 |
| `external_messaging.slack.board_mapping` | `dict[str, str]` | `{}` | channel_id → animaworks_board_name (자동 채워짐) |
| `external_messaging.slack.board_outbound_sync` | `list[str]` | `[]` | 이 플랫폼으로 아웃바운드 동기화할 보드 이름 (화이트리스트) |
| `external_messaging.slack.board_outbound_sync_all` | `bool` | `false` | 화이트리스트가 비어 있으면 매핑된 모든 보드 동기화에 옵트인 |
| `external_messaging.slack.guild_id` | `str` | `""` | Discord 길드 스노우플레이크 ID (Discord 전용) |
| `external_messaging.slack.channel_members` | `dict[str, list[str]]` | `{}` | channel_id → [anima_name, ...] (Discord 전용) |
| `external_messaging.slack.default_channel_company` | `str` | `""` | 자동 생성 보드의 회사 (비어 있으면 귀속 없음) |
| `external_messaging.chatwork` | `ExternalMessagingChannelConfig` | `{ExternalMessagingChannelConfig}` | — |
| `external_messaging.chatwork.enabled` | `bool` | `false` | — |
| `external_messaging.chatwork.mode` | `str` | `"socket"` | "socket" \| "webhook" |
| `external_messaging.chatwork.anima_mapping` | `dict[str, str]` | `{}` | channel_id → anima_name ("" = 이 채널 무시) |
| `external_messaging.chatwork.default_anima` | `str` | `""` | 매핑되지 않은 채널의 폴백 anima |
| `external_messaging.chatwork.app_id_mapping` | `dict[str, str]` | `{}` | api_app_id → anima_name (Anima별 웹훅 라우팅) |
| `external_messaging.chatwork.auto_response` | `bool` | `false` | LLM 응답을 원래 플랫폼으로 자동 게시 |
| `external_messaging.chatwork.board_mapping` | `dict[str, str]` | `{}` | channel_id → animaworks_board_name (자동 채워짐) |
| `external_messaging.chatwork.board_outbound_sync` | `list[str]` | `[]` | 이 플랫폼으로 아웃바운드 동기화할 보드 이름 (화이트리스트) |
| `external_messaging.chatwork.board_outbound_sync_all` | `bool` | `false` | 화이트리스트가 비어 있으면 매핑된 모든 보드 동기화에 옵트인 |
| `external_messaging.chatwork.guild_id` | `str` | `""` | Discord 길드 스노우플레이크 ID (Discord 전용) |
| `external_messaging.chatwork.channel_members` | `dict[str, list[str]]` | `{}` | channel_id → [anima_name, ...] (Discord 전용) |
| `external_messaging.chatwork.default_channel_company` | `str` | `""` | 자동 생성 보드의 회사 (비어 있으면 귀속 없음) |
| `external_messaging.discord` | `ExternalMessagingChannelConfig` | `{ExternalMessagingChannelConfig}` | — |
| `external_messaging.discord.enabled` | `bool` | `false` | — |
| `external_messaging.discord.mode` | `str` | `"socket"` | "socket" \| "webhook" |
| `external_messaging.discord.anima_mapping` | `dict[str, str]` | `{}` | channel_id → anima_name ("" = 이 채널 무시) |
| `external_messaging.discord.default_anima` | `str` | `""` | 매핑되지 않은 채널의 폴백 anima |
| `external_messaging.discord.app_id_mapping` | `dict[str, str]` | `{}` | api_app_id → anima_name (Anima별 웹훅 라우팅) |
| `external_messaging.discord.auto_response` | `bool` | `false` | LLM 응답을 원래 플랫폼으로 자동 게시 |
| `external_messaging.discord.board_mapping` | `dict[str, str]` | `{}` | channel_id → animaworks_board_name (자동 채워짐) |
| `external_messaging.discord.board_outbound_sync` | `list[str]` | `[]` | 이 플랫폼으로 아웃바운드 동기화할 보드 이름 (화이트리스트) |
| `external_messaging.discord.board_outbound_sync_all` | `bool` | `false` | 화이트리스트가 비어 있으면 매핑된 모든 보드 동기화에 옵트인 |
| `external_messaging.discord.guild_id` | `str` | `""` | Discord 길드 스노우플레이크 ID (Discord 전용) |
| `external_messaging.discord.channel_members` | `dict[str, list[str]]` | `{}` | channel_id → [anima_name, ...] (Discord 전용) |
| `external_messaging.discord.default_channel_company` | `str` | `""` | 자동 생성 보드의 회사 (비어 있으면 귀속 없음) |
| `external_messaging.zoom` | `ZoomRTMSConfig` | `{ZoomRTMSConfig}` | — |
| `external_messaging.zoom.enabled` | `bool` | `false` | — |
| `external_messaging.zoom.default_anima` | `str` | `""` | 매핑되지 않은 회의의 폴백 anima |
| `external_messaging.zoom.meeting_mapping` | `dict[str, str]` | `{}` | meeting_id → anima_name |
| `external_messaging.zoom.chunk_interval_seconds` | `int` | `300` | 버퍼링된 트랜스크립트의 플러시 간격 |
| `external_messaging.zoom.chunk_max_chars` | `int` | `4000` | 청크당 최대 문자 수 (먼저 도달하는 조건에서 플러시) |
| `external_tasks` | `ExternalTasksConfig` | `{ExternalTasksConfig}` | 외부 작업 시스템과의 연동. |
| `external_tasks.enabled` | `bool` | `true` | — |
| `external_tasks.interval_minutes` | `int` | `5` | — |
| `external_tasks.sources` | `ExternalTasksSourcesConfig` | `{ExternalTasksSourcesConfig}` | — |
| `external_tasks.sources.github` | `bool` | `true` | — |
| `external_tasks.sources.slack` | `bool` | `true` | — |
| `external_tasks.sources.chatwork` | `bool` | `true` | — |
| `external_tasks.sources.gmail` | `bool` | `true` | — |
| `github_webhook` | `GitHubWebhookConfig` | `{GitHubWebhookConfig}` | GitHub 웹훅의 수신과 검증. |
| `github_webhook.enabled` | `bool` | `false` | — |
| `github_webhook.repos` | `list[str]` | `[]` | — |
| `github_webhook.dispatcher_anima` | `str` | `"rin"` | — |
| `github_webhook.bot_login` | `str` | `""` | — |
| `github_webhook.reviewer_login` | `str` | `""` | — |
| `github_webhook.quiet_seconds` | `float` | `180` | — |
| `github_webhook.drop_bot_noise` | `bool` | `true` | — |
| `event_export` | `EventExportConfig` | `{EventExportConfig}` | 이벤트 데이터의 내보내기. |
| `event_export.url` | `str \| None` | `null` | — |
| `event_export.headers` | `dict[str, str]` | `{}` | — |
| `event_export.event_types` | `list[str] \| None` | `null` | — |
| `event_export.include_token_usage` | `bool` | `true` | — |
| `event_export.max_retries` | `int` | `8` | — |
| `event_export.backoff_base_seconds` | `float` | `2.0` | — |
| `event_export.spool_max_mb` | `int` | `64` | — |
| `background_task` | `BackgroundTaskConfig` | `{BackgroundTaskConfig}` | 백그라운드 실행 대상 도구 설정. |
| `background_task.enabled` | `bool` | `true` | — |
| `background_task.shutdown_drain_seconds` | `float` | `600.0` | — |
| `background_task.eligible_tools` | `dict[str, BackgroundToolConfig]` | `…` | — |
| `background_task.eligible_tools.threshold_s` | `int` | `30` | — |
| `background_task.result_memory_retention_minutes` | `int` | `60` | 프로세스 내 결과 캐시 |
| `background_task.max_completed_tasks_in_memory` | `int` | `200` | — |
| `background_task.worker_pool_size` | `int` | `1` | — |
| `activity_log` | `ActivityLogConfig` | `{ActivityLogConfig}` | 작업·활동 로그의 저장 설정. |
| `activity_log.rotation_enabled` | `bool` | `true` | — |
| `activity_log.rotation_mode` | `Literal['size', 'time', 'both']` | `"size"` | — |
| `activity_log.max_size_mb` | `int` | `1024` | anima별 총량, 기본 1GB |
| `activity_log.max_file_size_mb` | `int` | `100` | 파일당 비대화 트리거; 0 = 비활성화 |
| `activity_log.max_age_days` | `int` | `7` | mode="time"\|"both"에서 사용 |
| `activity_log.rotation_time` | `str` | `"05:00"` | 실행 시각 (설정된 TZ) |
| `logging` | `LoggingConfig` | `{LoggingConfig}` | 로그 레벨, 출력 대상, 민감 정보 마스킹. |
| `logging.redaction_enabled` | `bool` | `true` | 로그 출력에서 비밀 마스킹; 원시 로그 디버깅 시 비활성화. |
| `heartbeat` | `HeartbeatConfig` | `{HeartbeatConfig}` | 정기적인 heartbeat의 실행 설정. |
| `heartbeat.interval_minutes` | `int` | `30` | — |
| `heartbeat.current_state_max_chars` | `int` | `8000` | current_state.md의 최대 문자 수 (초과 시 트림); 0 = 비활성화 |
| `heartbeat.current_state_cleanup_chars` | `int` | `2000` | current_state.md의 소프트 정리 임계값; 0 = current_state_max_chars의 80% |
| `heartbeat.heartbeat_md_max_bytes` | `int` | `8000` | heartbeat.md의 최대 바이트 수 (초과 시 압축 지시가 heartbeat 프롬프트에 주입됨); 0 = 비활성화 |
| `heartbeat.recent_dialogue_max_age_hours` | `int` | `6` | 마지막 턴이 이 시간(시간)보다 최근일 때만 heartbeat 컨텍스트에 최근 채팅 대화 포함; 0 = 항상 포함 |
| `heartbeat.soft_timeout_seconds` | `int` | `300` | HB 세션에 마무리 시스템 알림을 주입하기 전 대기 시간(초) |
| `heartbeat.hard_timeout_seconds` | `int` | `0` | HB 세션을 강제 종료하기 전 대기 시간(초); 0 = 비활성화 |
| `heartbeat.default_model` | `str \| None` | `null` | heartbeat/cron용 전역 백그라운드 모델 (None = 메인 모델 사용) |
| `heartbeat.enable_read_ack` | `bool` | `false` | — |
| `heartbeat.delegation_dm_enabled` | `bool` | `true` | delegate_task는 이미 대상의 대기 설명자를 작성합니다; DM은 추가 받은 편지함 실행만 깨웁니다. 건너뛰려면 false로 설정. |
| `heartbeat.idle_compaction_minutes` | `float` | `10.0` | 마지막 스트림 종료 후 유휴 자동 압축을 트리거할 때까지의 분 |
| `heartbeat.resolved_interaction_reminder_hours` | `int` | `48` | 해결된 승인 알림을 시스템 프롬프트에 주입할 시간; 0 = 알림 섹션 비활성화 |
| `voice` | `VoiceConfig` | `{VoiceConfig}` | 음성 입출력과 음성 제공자. |
| `voice.stt_model` | `str` | `"large-v3-turbo"` | — |
| `voice.stt_device` | `str` | `"auto"` | — |
| `voice.stt_compute_type` | `str` | `"default"` | — |
| `voice.stt_language` | `str \| None` | `null` | — |
| `voice.stt_refine_enabled` | `bool` | `false` | — |
| `voice.default_tts_provider` | `str` | `"voicevox"` | — |
| `voice.front_model` | `str \| None` | `null` | — |
| `voice.front_api_base` | `str \| None` | `null` | — |
| `voice.proactive_enabled` | `bool` | `true` | — |
| `voice.proactive_initial_delay_sec` | `float` | `10.0` | — |
| `voice.proactive_lead_sec` | `float` | `5.0` | — |
| `voice.voicevox` | `VoicevoxConfig` | `{VoicevoxConfig}` | — |
| `voice.voicevox.base_url` | `str` | `"http://localhost:50021"` | — |
| `voice.elevenlabs` | `ElevenLabsVoiceConfig` | `{ElevenLabsVoiceConfig}` | — |
| `voice.elevenlabs.api_key_env` | `str` | `"ELEVENLABS_API_KEY"` | — |
| `voice.elevenlabs.model_id` | `str` | `"eleven_flash_v2_5"` | — |
| `voice.style_bert_vits2` | `StyleBertVits2Config` | `{StyleBertVits2Config}` | — |
| `voice.style_bert_vits2.base_url` | `str` | `"http://localhost:5000"` | — |
| `voice.irodori` | `IrodoriConfig` | `{IrodoriConfig}` | — |
| `voice.irodori.base_url` | `str` | `"http://localhost:7861"` | — |
| `voice.gemini` | `GeminiTTSVoiceConfig` | `{GeminiTTSVoiceConfig}` | — |
| `voice.gemini.model` | `str` | `"gemini-3.8-flash-tts"` | — |
| `voice.gemini.api_key_env` | `str` | `"GEMINI_API_KEY"` | — |
| `voice.gemini.vault_key` | `str` | `"GEMINI_API_KEY"` | — |
| `voice.gemini.chunk_seconds` | `float` | `1.0` | — |
| `housekeeping` | `HousekeepingConfig` | `{HousekeepingConfig}` | 런타임 데이터의 정기 정리. |
| `housekeeping.enabled` | `bool` | `true` | — |
| `housekeeping.run_time` | `str` | `"05:30"` | — |
| `housekeeping.prompt_log_retention_days` | `int` | `3` | — |
| `housekeeping.daemon_log_max_size_mb` | `int` | `50` | — |
| `housekeeping.daemon_log_keep_generations` | `int` | `5` | — |
| `housekeeping.anima_log_retention_days` | `int` | `30` | — |
| `housekeeping.anima_log_total_max_size_mb` | `int` | `200` | — |
| `housekeeping.frontend_log_backup_count` | `int` | `7` | — |
| `housekeeping.dm_log_archive_retention_days` | `int` | `30` | — |
| `housekeeping.cron_log_retention_days` | `int` | `14` | — |
| `housekeeping.shortterm_retention_days` | `int` | `7` | — |
| `housekeeping.shortterm_archive_retention_days` | `int` | `30` | — |
| `housekeeping.shortterm_thread_gc_days` | `int` | `30` | — |
| `housekeeping.facts_lock_stale_hours` | `int` | `24` | — |
| `housekeeping.curator_report_retention_days` | `int` | `30` | — |
| `housekeeping.task_results_retention_days` | `int` | `7` | — |
| `housekeeping.pending_failed_retention_days` | `int` | `14` | — |
| `housekeeping.corrupt_vectordb_keep_generations` | `int` | `2` | — |
| `housekeeping.tmp_retention_days` | `int` | `14` | — |
| `housekeeping.backup_retention_days` | `int` | `90` | — |
| `housekeeping.codex_log_max_size_mb` | `int` | `200` | — |
| `housekeeping.codex_tmp_retention_hours` | `int` | `12` | — |
| `housekeeping.anima_tmp_gitdirs_retention_days` | `int` | `14` | — |
| `housekeeping.anima_local_log_retention_days` | `int` | `30` | — |
| `housekeeping.pending_processing_stale_hours` | `int` | `24` | — |
| `housekeeping.background_running_stale_hours` | `int` | `48` | — |
| `housekeeping.current_state_stale_hours` | `int` | `24` | — |
| `housekeeping.suppressed_messages_max_size_mb` | `int` | `10` | — |
| `housekeeping.suppressed_messages_keep_generations` | `int` | `5` | — |
| `housekeeping.sdk_bash_injection_max_size_mb` | `int` | `10` | — |
| `housekeeping.archive_superseded_retention_days` | `int` | `7` | — |
| `housekeeping.archive_versions_keep_per_file` | `int` | `5` | — |
| `inbox` | `InboxConfig` | `{InboxConfig}` | anima의 받은 편지함과 알림 표시. |
| `inbox.ttl_hours` | `float` | `24.0` | — |
| `inbox.expired_retention_days` | `int` | `7` | — |
| `inbox.processed_retention_days` | `int` | `30` | — |
| `inbox.quarantine_retention_days` | `int` | `30` | — |
| `local_llm` | `LocalLLMConfig` | `{LocalLLMConfig}` | 로컬 LLM 엔드포인트와 모델 설정. |
| `local_llm.base_url` | `str` | `"http://127.0.0.1:11434"` | — |
| `local_llm.default_model` | `str` | `"ollama/qwen2.5-coder:14b"` | — |
| `local_llm.credential` | `str` | `""` | — |
| `local_llm.auto_apply_presets` | `bool` | `false` | — |
| `local_llm.presets` | `dict[str, str]` | `{"coding":"ollama/qwen2.5-coder:14b","general":"ollama/glm4:9b","reasoning":"ollama/deepseek-r1:8b"}` | — |
| `local_llm.role_presets` | `dict[str, str]` | `…` | — |
| `workspaces` | `dict[str, str]` | `{}` | 이름 있는 workspace 경로의 대응. |
| `github_identities` | `dict[str, str]` | `{}` | 회사 slug와 GitHub 계정의 대응. |
| `activity_level` | `int` | `100` | 전체 활동 빈도를 조정하는 배율. |
| `activity_schedule` | `list[ActivityScheduleEntry]` | `[]` | 시간대별 활동 빈도. |
| `activity_schedule.start` | `str` | `"—"` | 시작 시간 (HH:MM 형식) |
| `activity_schedule.end` | `str` | `"—"` | 종료 시간 (HH:MM 형식, 자정을 넘길 수 있음) |
| `activity_schedule.level` | `int` | `"—"` | 이 기간의 활동 수준 백분율 |
| `icon_url_template` | `str` | `""` | anima 아이콘 URL의 템플릿. |
| `ui` | `UIConfig` | `{UIConfig}` | Web UI의 표시 설정. |
| `ui.theme` | `str` | `"default"` | — |
| `ui.demo_mode` | `bool` | `false` | — |

## anima별 `status.json`

| 키 | ModelConfig 형식 | 기본값 | 설명 |
|---|---|---|---|
| `background_credential` | `str \| None` | `null` | — |
| `background_model` | `str \| None` | `null` | heartbeat 및 cron에서 사용할 모델 재정의. |
| `background_thinking_effort` | `str \| None` | `null` | — |
| `consolidation_enabled` | `—` | `—` | — |
| `context_absolute_ceiling` | `float` | `0.75` | — |
| `context_threshold` | `float` | `0.5` | — |
| `conversation_history_threshold` | `float` | `0.3` | — |
| `credential` | `str \| None` | `null` | anima에 연결할 인증 정보 이름. |
| `default_workspace` | `—` | `—` | — |
| `execution_mode` | `str \| None` | `null` | anima의 실행 모드. |
| `extra_mcp_servers` | `dict[str, dict]` | `{}` | — |
| `fallback_model` | `str \| None` | `null` | 기본 모델 실패 시 사용할 대체 모델. |
| `fallback_models` | `list[str]` | `[]` | — |
| `heartbeat_enabled` | `bool` | `true` | 정기 heartbeat 활성화 여부. |
| `max_session_age_hours` | `float` | `24.0` | — |
| `max_tokens` | `int` | `8192` | 모델의 최대 출력 토큰 수. |
| `mode_s_auth` | `str \| None` | `null` | — |
| `model` | `str` | `"claude-sonnet-4-6"` | anima의 기본 모델. |
| `supervisor` | `str \| None` | `null` | 상위 supervisor anima의 이름. |
| `task_compaction_max` | `int` | `6` | — |
| `task_compaction_tokens` | `int` | `0` | — |
| `thinking` | `bool \| None` | `null` | — |
| `thinking_effort` | `str \| None` | `null` | — |
| `token_budget_monthly` | `int \| None` | `null` | — |
| `voice_thinking_effort` | `str \| None` | `null` | — |
| `bootstrap_state` | `—` | `—` | 초기화 처리 상태. |
| `company` | `—` | `—` | 소속 회사. |
| `department` | `—` | `—` | 소속 부서. |
| `enabled` | `—` | `—` | anima 활성화 여부. |
| `needs_user_input` | `—` | `—` | 사용자 입력이 필요한 상태인지 여부. |
| `role` | `—` | `—` | anima의 역할 템플릿. |

## `models.json`

모델 이름 패턴별 실행 모드와 컨텍스트 윈도우입니다.

| 모델 이름 패턴 | 모드 | 컨텍스트 윈도우 |
|---|---|---:|
| `anthropic/claude-*` | `A` | 200000 |
| `azure/*` | `A` | 128000 |
| `azure/gpt-4.1*` | `A` | 1000000 |
| `bedrock/*` | `A` | 200000 |
| `bedrock/meta.llama4*` | `A` | 1000000 |
| `bedrock/qwen.*` | `A` | 131072 |
| `claude-*` | `S` | 200000 |
| `claude-opus-4-6` | `S` | 200000 |
| `claude-sonnet-4-6` | `S` | 200000 |
| `codex/*` | `C` | 128000 |
| `codex/gpt-4.1` | `C` | 1000000 |
| `codex/gpt-5.4` | `C` | 272000 |
| `codex/o3` | `C` | 200000 |
| `codex/o4-mini` | `C` | 200000 |
| `cursor/*` | `D` | 1000000 |
| `deepseek/deepseek-chat` | `A` | 128000 |
| `gemini/*` | `G` | 1000000 |
| `google/*` | `A` | 1000000 |
| `grok/*` | `X` | 500000 |
| `grok/grok-4.5` | `X` | 500000 |
| `mistral/*` | `A` | 256000 |
| `nanogpt/*` | `A` | 128000 |
| `ollama/*` | `A` | 8192 |
| `ollama/gemma3*` | `A` | 8192 |
| `ollama/glm-4.7*` | `A` | 32768 |
| `ollama/glm-5*` | `A` | 32768 |
| `ollama/kimi-k2*` | `A` | 131072 |
| `ollama/llama4:*` | `A` | 131072 |
| `ollama/phi4*` | `A` | 16384 |
| `ollama/qwen3-coder:*` | `A` | 40960 |
| `ollama/qwen3:14b` | `A` | 40960 |
| `ollama/qwen3:30b` | `A` | 40960 |
| `ollama/qwen3:32b` | `A` | 40960 |
| `openai/*` | `A` | 128000 |
| `openai/deepseek-v4-flash` | `A` | 1048576 |
| `openai/deepseek-v4-flash-0731` | `A` | 1048576 |
| `openai/gpt-4.1*` | `A` | 1000000 |
| `openai/gpt-5.4*` | `A` | 272000 |
| `openai/qwen3.5*` | `A` | 64000 |
| `openai/qwen3.6-27b*` | `A` | 32768 |
| `openai/qwen3.6-35b*` | `A` | 32768 |
| `openai/zai.glm*` | `A` | 131072 |
| `vertex_ai/*` | `A` | 1000000 |
| `xai/*` | `A` | 256000 |
