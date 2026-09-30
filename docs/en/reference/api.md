<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/api.md -->
<!-- i18n: source-sha256=f369c6dcfdbdd7a840b46018630e53fc3baa21ce283a14b755228f872d1c5211 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

# API Reference

Generated from FastAPI's OpenAPI definitions, WebSocket, and `server/app.py`'s direct routes.

| Method | Path | Authentication Category | Summary | Definition Location |
|---|---|---|---|---|

## `server/app.py`

| GET | `/` | Not required | — | `server/app.py:_serve_index` |
| GET | `/_v/{version}/{path:path}` | Not required | — | `server/app.py:_serve_versioned_static` |
| GET | `/api/workspace/pixel/assets/{path:path}` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | — | `server/app.py:_pixel_workspace_asset` |
| GET | `/api/workspace/pixel/scene` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | — | `server/app.py:_pixel_workspace_scene` |
| GET | `/battle` | Not required | — | `server/app.py:_serve_battle_index` |
| GET | `/battle/` | Not required | — | `server/app.py:_serve_battle_index` |
| GET | `/health` | Not required (exclusion list) | — | `server/app.py:_health` |
| GET | `/setup` | Not required | — | `server/app.py:_serve_setup_index` |
| GET | `/setup/` | Not required | — | `server/app.py:_serve_setup_index` |
| GET | `/startup-status` | Not required | — | `server/app.py:_startup_status` |
| GET | `/workspace` | Not required | — | `server/app.py:_serve_workspace_index` |
| GET | `/workspace/` | Not required | — | `server/app.py:_serve_workspace_index` |
| GET | `/workspace/pixel` | Not required | — | `server/app.py:_redirect_pixel_workspace` |
| GET | `/workspace/pixel/` | Not required | — | `server/app.py:_serve_pixel_workspace_index` |

## `server/routes/animas.py`

| GET | `/api/animas` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Retrieves the list of available animas. | `server/routes/animas.py:list_animas` |
| POST | `/api/animas/reload-all` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Hot-reload ModelConfig for all running animas. | `server/routes/animas.py:reload_all_anima_configs` |
| DELETE | `/api/animas/{name}` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Stop and delete an anima entirely (process + files). | `server/routes/animas.py:delete_anima` |
| GET | `/api/animas/{name}` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | — | `server/routes/animas.py:get_anima_detail` |
| GET | `/api/animas/{name}/aliases` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Return aliases for an anima from config.json. | `server/routes/animas.py:get_anima_aliases` |
| PUT | `/api/animas/{name}/aliases` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Update aliases for an anima in config.json. | `server/routes/animas.py:update_anima_aliases` |
| GET | `/api/animas/{name}/background-tasks` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | List background tasks for an anima (reads from state dir). | `server/routes/animas.py:list_background_tasks` |
| GET | `/api/animas/{name}/background-tasks/{task_id}` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Get a specific background task by ID. | `server/routes/animas.py:get_background_task` |
| GET | `/api/animas/{name}/config` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Return resolved model configuration for an anima. | `server/routes/animas.py:get_anima_config` |
| GET | `/api/animas/{name}/cron` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Return the raw cron.md content for an anima. | `server/routes/animas.py:get_anima_cron` |
| POST | `/api/animas/{name}/disable` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Disable an Anima (set status.json to enabled: false and stop process). | `server/routes/animas.py:disable_anima` |
| POST | `/api/animas/{name}/enable` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Enable an Anima (set status.json to enabled: true). | `server/routes/animas.py:enable_anima` |
| GET | `/api/animas/{name}/heartbeat` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Return the raw heartbeat.md content for an anima. | `server/routes/animas.py:get_anima_heartbeat` |
| PUT | `/api/animas/{name}/identity` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Update the identity.md content for an anima. | `server/routes/animas.py:update_anima_identity` |
| PUT | `/api/animas/{name}/injection` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Update the injection.md content for an anima. | `server/routes/animas.py:update_anima_injection` |
| POST | `/api/animas/{name}/interactions/{callback_id}/resolve` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Resolve an interactive call_human request from the main chat UI. | `server/routes/animas.py:resolve_interaction` |
| POST | `/api/animas/{name}/interrupt` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Interrupt the current LLM session without stopping the process. | `server/routes/animas.py:interrupt_anima` |
| PUT | `/api/animas/{name}/model` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Update the model setting in status.json for an anima. | `server/routes/animas.py:update_anima_model` |
| GET | `/api/animas/{name}/permissions` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Return permissions.json for an anima. | `server/routes/animas.py:get_anima_permissions` |
| PUT | `/api/animas/{name}/permissions` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Update permissions.json for an anima. | `server/routes/animas.py:update_anima_permissions` |
| POST | `/api/animas/{name}/reload` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Hot-reload ModelConfig from status.json without process restart. | `server/routes/animas.py:reload_anima_config` |
| POST | `/api/animas/{name}/restart` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Restart a specific anima process. | `server/routes/animas.py:restart_anima` |
| POST | `/api/animas/{name}/start` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Start a stopped anima process. | `server/routes/animas.py:start_anima` |
| POST | `/api/animas/{name}/stop` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Stop a specific anima process. | `server/routes/animas.py:stop_anima` |
| POST | `/api/animas/{name}/trigger` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | — | `server/routes/animas.py:trigger_heartbeat` |
| GET | `/api/org/chart` | Session required (can be omitted in local_trust mode, or if localhost trust is enabled) | Return the organisation chart as a tree-structured JSON. | `server/routes/animas.py:get_org_chart` |

## `server/routes/approve.py`

| GET | `/api/approve/{callback_id}` | Not required (exclusion list) | Serve the approval page for a given callback_id. | `server/routes/approve.py:get_approval_page` |
| POST | `/api/approve/{callback_id}` | Not required (exclusion list) | Process an approval decision from the web page. | `server/routes/approve.py:submit_approval` |

## `server/routes/assets.py`

| GET | `/api/animas/{name}/assets` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List available assets for an anima. | `server/routes/assets.py:list_assets` |
| POST | `/api/animas/{name}/assets/generate` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Trigger character asset generation pipeline. | `server/routes/assets.py:generate_assets` |
| POST | `/api/animas/{name}/assets/generate-expression` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Generate a specific bustup expression variant on demand. | `server/routes/assets.py:generate_expression_on_demand` |
| GET | `/api/animas/{name}/assets/metadata` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Return structured metadata about a anima's available assets. | `server/routes/assets.py:get_asset_metadata` |
| POST | `/api/animas/{name}/assets/regenerate-step` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Regenerate one pipeline step (fullbody, bustup, icon, chibi, 3d, rigging, animations). | `server/routes/assets.py:regenerate_asset_step` |
| POST | `/api/animas/{name}/assets/remake-confirm` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Accept the preview and cascade-rebuild all remaining assets. | `server/routes/assets.py:remake_confirm` |
| DELETE | `/api/animas/{name}/assets/remake-preview` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Cancel a remake preview by restoring from the most recent backup. | `server/routes/assets.py:cancel_remake_preview` |
| GET | `/api/animas/{name}/assets/remake-preview` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List generated preview files. | `server/routes/assets.py:list_remake_previews` |
| POST | `/api/animas/{name}/assets/remake-preview` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Generate a fullbody preview, optionally using Vibe Transfer. | `server/routes/assets.py:remake_preview` |
| POST | `/api/animas/{name}/assets/upload-fullbody` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Upload a PNG/JPEG to overwrite the anima's full-body reference image. | `server/routes/assets.py:upload_fullbody_asset` |
| GET | `/api/animas/{name}/assets/{filename}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Serve a static asset file from a anima's assets directory. | `server/routes/assets.py:get_asset` |
| HEAD | `/api/animas/{name}/assets/{filename}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Serve a static asset file from a anima's assets directory. | `server/routes/assets.py:get_asset` |
| GET | `/api/animas/{name}/attachments/{filename}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Serve a user-uploaded attachment from a anima's attachments directory. | `server/routes/assets.py:get_attachment` |
| HEAD | `/api/animas/{name}/attachments/{filename}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Serve a user-uploaded attachment from a anima's attachments directory. | `server/routes/assets.py:get_attachment` |
| GET | `/api/media/proxy` | Session required (optional in local_trust mode, or if localhost trust is enabled) | — | `server/routes/assets.py:media_proxy` |

## `server/routes/auth.py`

| POST | `/api/auth/login` | Not required (excluded list) | Validate authentication credentials and start a session. | `server/routes/auth.py:login` |
| POST | `/api/auth/logout` | Session required (optional in local_trust mode, or if localhost trust is enabled) | — | `server/routes/auth.py:logout` |
| GET | `/api/auth/me` | Session required (optional in local_trust mode, or if localhost trust is enabled) | — | `server/routes/auth.py:me` |

## `server/routes/channels.py`

| GET | `/api/channels` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List all shared channels with metadata including ACL info. | `server/routes/channels.py:list_channels` |
| GET | `/api/channels/{name}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get messages from a specific channel. | `server/routes/channels.py:get_channel_messages` |
| POST | `/api/channels/{name}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Post a message to a channel (human-originated). | `server/routes/channels.py:post_to_channel` |
| GET | `/api/channels/{name}/mentions/{anima}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get messages mentioning a specific anima in a channel. | `server/routes/channels.py:get_channel_mentions` |
| GET | `/api/dm` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List all DM conversation pairs with metadata. | `server/routes/channels.py:list_dm_pairs` |
| GET | `/api/dm/{pair}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get DM history for a specific pair. | `server/routes/channels.py:get_dm_history` |

## `server/routes/chat.py`

| POST | `/api/animas/{name}/chat` | Session required (optional in local_trust mode, or if localhost trust is enabled) | — | `server/routes/chat.py:chat` |
| POST | `/api/animas/{name}/chat/compact` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Manually compact a chat thread's context on demand. | `server/routes/chat.py:compact_session` |
| POST | `/api/animas/{name}/chat/stream` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Stream chat response via SSE over IPC. | `server/routes/chat.py:chat_stream` |
| POST | `/api/animas/{name}/greet` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Generate a greeting when user clicks the character. | `server/routes/chat.py:greet` |
| GET | `/api/animas/{name}/stream/active` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Return the active (or most recent) stream for an anima. | `server/routes/chat.py:get_active_stream` |
| GET | `/api/animas/{name}/stream/{response_id}/progress` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Return progress of a specific stream. | `server/routes/chat.py:get_stream_progress` |

## `server/routes/chat_ui_state.py`

| GET | `/api/chat/ui-state` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get persisted dashboard chat UI state for current user. | `server/routes/chat_ui_state.py:get_chat_ui_state` |
| PUT | `/api/chat/ui-state` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Persist dashboard chat UI state for current user. | `server/routes/chat_ui_state.py:put_chat_ui_state` |

## `server/routes/config_routes.py`

| GET | `/api/discord/channel-members` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return all Discord channel membership mappings. | `server/routes/config_routes.py:get_discord_channel_members` |
| PUT | `/api/discord/channel-members/{channel_id}` | Session required (local_trust mode, or optional if localhost trust is enabled) | Update Anima members for a Discord channel. | `server/routes/config_routes.py:put_discord_channel_members` |
| GET | `/api/discord/channels` | Session required (local_trust mode, or optional if localhost trust is enabled) | List Discord guild channels with membership info. | `server/routes/config_routes.py:get_discord_channels` |
| GET | `/api/settings/anthropic-auth` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return current Anthropic auth mode and runtime availability. | `server/routes/config_routes.py:get_anthropic_auth` |
| PUT | `/api/settings/anthropic-auth` | Session required (local_trust mode, or optional if localhost trust is enabled) | Persist Anthropic auth mode in config.json for the settings UI. | `server/routes/config_routes.py:update_anthropic_auth` |
| GET | `/api/settings/openai-auth` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return current OpenAI auth mode and runtime availability. | `server/routes/config_routes.py:get_openai_auth` |
| PUT | `/api/settings/openai-auth` | Session required (local_trust mode, or optional if localhost trust is enabled) | Persist OpenAI auth mode in config.json for the settings UI. | `server/routes/config_routes.py:update_openai_auth` |
| GET | `/api/system/available-models` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return all available models (cloud + local) for UI dropdowns. | `server/routes/config_routes.py:get_available_models` |
| GET | `/api/system/available-tools` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return available external tool module names (minus disabled services). | `server/routes/config_routes.py:get_available_tools` |
| GET | `/api/system/config` | Session required (local_trust mode, or optional if localhost trust is enabled) | Read and return the AnimaWorks config with masked secrets. | `server/routes/config_routes.py:get_config` |

## `server/routes/external_tasks.py`

| GET | `/api/external-tasks` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get external tasks for the widget from the snapshot store. | `server/routes/external_tasks.py:get_external_tasks` |

## `server/routes/internal.py`

| POST | `/api/internal/anima/create` | Internal | Create an anima outside sandbox EROFS constraints. | `server/routes/internal.py:internal_anima_create` |
| POST | `/api/internal/call-human/confirm` | Internal | Check the CLI ``call_human`` confirmation key; keys live in server memory only. | `server/routes/internal.py:internal_call_human_confirm` |
| GET | `/api/internal/company/boundary` | Internal | Resolve company membership on the host for sandboxed handlers. | `server/routes/internal.py:internal_company_boundary` |
| POST | `/api/internal/delegate-task` | Internal | Persist a delegated task outside sandbox EROFS constraints. | `server/routes/internal.py:internal_delegate_task` |
| POST | `/api/internal/embed` | Internal | Centralized embedding inference for child processes. | `server/routes/internal.py:internal_embed` |
| POST | `/api/internal/interaction/create` | Internal | — | `server/routes/internal.py:internal_interaction_create` |
| POST | `/api/internal/interaction/message-ts` | Internal | — | `server/routes/internal.py:internal_interaction_message_ts` |
| POST | `/api/internal/message-sent` | Internal | Notify the server that a message was sent via CLI. | `server/routes/internal.py:internal_message_sent` |
| POST | `/api/internal/notification-mapping` | Internal | — | `server/routes/internal.py:internal_notification_mapping` |
| POST | `/api/internal/post-channel` | Internal | Append a channel post outside sandbox EROFS constraints. | `server/routes/internal.py:internal_post_channel` |
| POST | `/api/internal/rerank` | Internal | Centralized cross-encoder reranking for child processes. | `server/routes/internal.py:internal_rerank` |
| POST | `/api/internal/send-message` | Internal | Persist a DM outside sandbox EROFS constraints. | `server/routes/internal.py:internal_send_message` |
| POST | `/api/internal/submit-tasks` | Internal | Publish a complete batch on the host; no sandbox DB grant is needed. | `server/routes/internal.py:internal_submit_tasks` |
| POST | `/api/internal/task-board-action` | Internal | Run a lease-guarded task board write for a sandboxed anima CLI. | `server/routes/internal.py:internal_task_board_action` |
| GET | `/api/internal/tasks` | Internal | Read a task snapshot for workers without direct database access. | `server/routes/internal.py:internal_tasks` |
| POST | `/api/internal/update-task` | Internal | Persist a task update outside sandbox EROFS constraints. | `server/routes/internal.py:internal_update_task` |
| POST | `/api/internal/vector/count` | Internal | — | `server/routes/internal.py:vector_count` |
| POST | `/api/internal/vector/create-collection` | Internal | — | `server/routes/internal.py:vector_create_collection` |
| POST | `/api/internal/vector/delete-collection` | Internal | — | `server/routes/internal.py:vector_delete_collection` |
| POST | `/api/internal/vector/delete-documents` | Internal | — | `server/routes/internal.py:vector_delete_documents` |
| POST | `/api/internal/vector/get-all` | Internal | — | `server/routes/internal.py:vector_get_all` |
| POST | `/api/internal/vector/get-by-ids` | Internal | — | `server/routes/internal.py:vector_get_by_ids` |
| POST | `/api/internal/vector/get-by-metadata` | Internal | — | `server/routes/internal.py:vector_get_by_metadata` |
| POST | `/api/internal/vector/list-collections` | Internal | — | `server/routes/internal.py:vector_list_collections` |
| POST | `/api/internal/vector/query` | Internal | Execute vector search for internal services. | `server/routes/internal.py:vector_query` |
| POST | `/api/internal/vector/update-metadata` | Internal | — | `server/routes/internal.py:vector_update_metadata` |
| POST | `/api/internal/vector/upsert` | Internal | — | `server/routes/internal.py:vector_upsert` |
| GET | `/api/messages/{message_id}` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return the full JSON of a stored message by its ID. | `server/routes/internal.py:get_message` |

## `server/routes/logs_routes.py`

| GET | `/api/system/logs` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List available log files. | `server/routes/logs_routes.py:list_logs` |
| GET | `/api/system/logs/file/read` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Read log file by basename or relative path from list endpoint. | `server/routes/logs_routes.py:read_log_by_ref` |
| GET | `/api/system/logs/stream` | Session required (optional in local_trust mode, or if localhost trust is enabled) | SSE endpoint for real-time log streaming (tail -f style). | `server/routes/logs_routes.py:stream_logs` |
| GET | `/api/system/logs/{filename}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Read log file content with pagination. | `server/routes/logs_routes.py:read_log` |

## `server/routes/memory_routes.py`

| DELETE | `/api/animas/{name}/conversation` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | Clear conversation history for a fresh start. | `server/routes/memory_routes.py:clear_conversation` |
| GET | `/api/animas/{name}/conversation` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | View current conversation state. | `server/routes/memory_routes.py:get_conversation` |
| POST | `/api/animas/{name}/conversation/compress` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | Manually trigger conversation compression. | `server/routes/memory_routes.py:compress_conversation` |
| GET | `/api/animas/{name}/episodes` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | — | `server/routes/memory_routes.py:list_episodes` |
| GET | `/api/animas/{name}/episodes/calendar` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | Return lightweight episode availability for every day in a month. | `server/routes/memory_routes.py:episode_calendar` |
| GET | `/api/animas/{name}/episodes/{date}` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | — | `server/routes/memory_routes.py:get_episode` |
| GET | `/api/animas/{name}/knowledge` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | — | `server/routes/memory_routes.py:list_knowledge` |
| GET | `/api/animas/{name}/knowledge/{topic}` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | — | `server/routes/memory_routes.py:get_knowledge` |
| GET | `/api/animas/{name}/memory/graph` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | Return the explicit-link memory graph for UI display. | `server/routes/memory_routes.py:memory_graph` |
| GET | `/api/animas/{name}/memory/stats` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | Return memory storage statistics for an anima. | `server/routes/memory_routes.py:memory_stats` |
| GET | `/api/animas/{name}/procedures` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | — | `server/routes/memory_routes.py:list_procedures` |
| GET | `/api/animas/{name}/procedures/{proc}` | Session required (may be omitted in local_trust mode or if localhost trust is enabled) | — | `server/routes/memory_routes.py:get_procedure` |

## `server/routes/room.py`

| GET | `/api/rooms` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List meeting rooms. | `server/routes/room.py:list_rooms` |
| POST | `/api/rooms` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Create a new meeting room. | `server/routes/room.py:create_room` |
| GET | `/api/rooms/{room_id}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get room details including conversation. | `server/routes/room.py:get_room` |
| POST | `/api/rooms/{room_id}/chat/stream` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Main SSE streaming endpoint for meeting chat. | `server/routes/room.py:meeting_chat_stream` |
| POST | `/api/rooms/{room_id}/close` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Close room and generate minutes. | `server/routes/room.py:close_room` |
| POST | `/api/rooms/{room_id}/participants` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Add a participant to the room. | `server/routes/room.py:add_participant` |
| DELETE | `/api/rooms/{room_id}/participants/{name}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Remove a participant from the room. | `server/routes/room.py:remove_participant` |

## `server/routes/sessions.py`

| GET | `/api/animas/{name}/conversation/history` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get conversation history from activity log. | `server/routes/sessions.py:get_conversation_history` |
| GET | `/api/animas/{name}/sessions` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List all available sessions: active conversation, archives, episodes. | `server/routes/sessions.py:list_sessions` |
| GET | `/api/animas/{name}/sessions/{session_id}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get archived session detail. | `server/routes/sessions.py:get_session_detail` |
| GET | `/api/animas/{name}/transcripts/{date}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Get full conversation transcript for a specific date. | `server/routes/sessions.py:get_transcript` |

## `server/routes/setup.py`

| POST | `/api/setup/codex/device-login` | Not required (excluded list) | Return browser-based device auth instructions for Codex login. | `server/routes/setup.py:start_codex_device_login` |
| POST | `/api/setup/complete` | Not required (excluded list) | Finalize setup: save config, create anima, mark complete. | `server/routes/setup.py:complete_setup` |
| GET | `/api/setup/detect-locale` | Not required (excluded list) | Detect locale from Accept-Language header. | `server/routes/setup.py:detect_locale` |
| GET | `/api/setup/environment` | Not required (excluded list) | Return environment information for the setup wizard. | `server/routes/setup.py:get_environment` |
| POST | `/api/setup/validate-key` | Not required (excluded list) | Validate an API key by making a small test request. | `server/routes/setup.py:validate_key` |

## `server/routes/skills.py`

| GET | `/api/animas/{name}/skills` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List visible skills for an anima and mark thread-local active entries. | `server/routes/skills.py:list_skills` |
| GET | `/api/animas/{name}/skills/active` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Return the active skills currently configured for a chat thread. | `server/routes/skills.py:get_active_skills` |
| PUT | `/api/animas/{name}/skills/active` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Replace active skills for a chat thread. | `server/routes/skills.py:update_active_skills` |
| POST | `/api/animas/{name}/skills/trust` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Promote a safe skill to trusted operating guidance. | `server/routes/skills.py:trust_skill` |

## `server/routes/system.py`

| GET | `/api/activity/group` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return one complete trigger-based activity group by stable ID. | `server/routes/system.py:get_activity_group` |
| GET | `/api/activity/recent` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return recent activity events from unified ActivityLogger. | `server/routes/system.py:get_recent_activity` |
| GET | `/api/activity/running-tasks` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return active background TaskExec workers grouped by Anima. | `server/routes/system.py:get_running_activity_tasks` |
| GET | `/api/settings/activity-level` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return the current global activity level and schedule. | `server/routes/system.py:get_activity_level` |
| PUT | `/api/settings/activity-level` | Session required (local_trust mode, or optional if localhost trust is enabled) | Update global activity level and reschedule all heartbeats. | `server/routes/system.py:set_activity_level` |
| PUT | `/api/settings/activity-schedule` | Session required (local_trust mode, or optional if localhost trust is enabled) | Update the time-based activity schedule (night mode). | `server/routes/system.py:set_activity_schedule` |
| POST | `/api/settings/display-mode` | Session required (local_trust mode, or optional if localhost trust is enabled) | Update display mode and sync config.image_gen.image_style. | `server/routes/system.py:set_display_mode` |
| GET | `/api/shared/users` | Session required (local_trust mode, or optional if localhost trust is enabled) | List registered user names from shared/users/. | `server/routes/system.py:list_shared_users` |
| GET | `/api/system/connections` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return WebSocket and process connection info. | `server/routes/system.py:system_connections` |
| GET | `/api/system/frontend-logs` | Session required (local_trust mode, or optional if localhost trust is enabled) | Read frontend logs from JSONL files with optional filters. | `server/routes/system.py:view_frontend_logs` |
| POST | `/api/system/frontend-logs` | Session required (local_trust mode, or optional if localhost trust is enabled) | Receive a batch of frontend log entries and write to daily JSONL. | `server/routes/system.py:receive_frontend_logs` |
| GET | `/api/system/health` | Not required (exclusion list) | Simple health check endpoint. | `server/routes/system.py:health_check` |
| POST | `/api/system/hot-reload/credentials` | Session required (local_trust mode, or optional if localhost trust is enabled) | Hot-reload credentials and dependent connections. | `server/routes/system.py:hot_reload_credentials` |
| POST | `/api/system/hot-reload/slack` | Session required (local_trust mode, or optional if localhost trust is enabled) | Hot-reload Slack Socket Mode connections only. | `server/routes/system.py:hot_reload_slack` |
| GET | `/api/system/log-level` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return the current root log level. | `server/routes/system.py:get_log_level` |
| POST | `/api/system/log-level` | Session required (local_trust mode, or optional if localhost trust is enabled) | Change the log level at runtime (no restart required). | `server/routes/system.py:set_log_level` |
| POST | `/api/system/reload` | Session required (local_trust mode, or optional if localhost trust is enabled) | Full sync: add new animas, refresh existing, remove deleted. | `server/routes/system.py:reload_animas` |
| POST | `/api/system/rewrite-runtime-refs` | Session required (local_trust mode, or optional if localhost trust is enabled) | Synchronize live caches after REWRITE_REFS updates disk state. | `server/routes/system.py:rewrite_runtime_refs` |
| GET | `/api/system/scheduler` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return scheduler status and job information. | `server/routes/system.py:system_scheduler` |
| GET | `/api/system/status` | Session required (local_trust mode, or optional if localhost trust is enabled) | — | `server/routes/system.py:system_status` |
| GET | `/api/system/token-budget` | Session required (local_trust mode, or optional if localhost trust is enabled) | Return current-month token budget status for each Anima. | `server/routes/system.py:get_token_budget` |

## `server/routes/taskboard.py`

| GET | `/api/task-board` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Return the unified TaskBoard view read straight from the canonical TaskStore. | `server/routes/taskboard.py:list_task_board` |
| GET | `/api/task-board/summary` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Return TaskBoard summary counts for dashboard use. | `server/routes/taskboard.py:get_task_board_summary` |
| POST | `/api/task-board/{anima_name}/{task_id}/cancel` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Explicitly cancel a task, overriding any outstanding lease (human operation). | `server/routes/taskboard.py:cancel_task` |

## `server/routes/usage_routes.py`

| GET | `/api/usage` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Return combined Claude + OpenAI + nanoGPT usage data. | `server/routes/usage_routes.py:get_usage` |
| POST | `/api/usage/claude/relogin` | Session required (optional in local_trust mode, or if localhost trust is enabled) | — | `server/routes/usage_routes.py:relogin_claude` |
| POST | `/api/usage/openai/relogin` | Session required (optional in local_trust mode, or if localhost trust is enabled) | — | `server/routes/usage_routes.py:relogin_openai` |

## `server/routes/users.py`

| GET | `/api/users` | Session required (optional in local_trust mode, or if localhost trust is enabled) | List all users (without password hashes). | `server/routes/users.py:list_users` |
| POST | `/api/users` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Add a new user (owner only). | `server/routes/users.py:add_user` |
| PUT | `/api/users/me/password` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Change (or initially set) the current user's password. | `server/routes/users.py:change_password` |
| DELETE | `/api/users/{username}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Delete a user (owner only, cannot delete self). | `server/routes/users.py:delete_user` |

## `server/routes/voice.py`

| WS | `/ws/voice/{name}` | Session required (optional in local_trust mode, or if localhost trust is enabled) | Voice conversation WebSocket for a specific Anima. | `server/routes/voice.py:voice_websocket` |

## `server/routes/webhooks.py`

| POST | `/api/webhooks/chatwork` | Not required (excluded list) | Handle Chatwork Webhook notifications. | `server/routes/webhooks.py:chatwork_webhook` |
| POST | `/api/webhooks/github` | Not required (excluded list) | Authenticate and enqueue a GitHub webhook event. | `server/routes/webhooks.py:github_webhook` |
| POST | `/api/webhooks/slack/events` | Not required (excluded list) | Handle Slack Event Subscriptions. | `server/routes/webhooks.py:slack_events` |
| POST | `/api/webhooks/zoom` | Not required (excluded list) | Handle Zoom RTMS webhook notifications. | `server/routes/webhooks.py:zoom_webhook` |
| GET | `/api/webhooks/zoom/oauth-callback` | Not required (excluded list) | Landing page for the Zoom OAuth redirect. | `server/routes/webhooks.py:zoom_oauth_callback` |

## `server/routes/websocket_route.py`

| WS | `/ws` | Session required (optional in local_trust mode, or if localhost trust is enabled) | — | `server/routes/websocket_route.py:websocket_endpoint` |
