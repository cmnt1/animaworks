# Priming Channel Technical Reference

Priming operates through a single compact path. It retrieves the sender, task, resident knowledge, recent sends, and human-facing notifications, and searches for related knowledge when conditions are met. For heartbeat / inbox / cron, it also retrieves recent activity and episodes according to the shared limits.

`PrimingEngine` describes the channels and budgets retrieved. C0 (important_knowledge) is an auxiliary block within Channel C’s knowledge pipeline.

## Channel List

| Channel | Source | trust |
|---------|--------|-------|
| A: sender_profile | `shared/users/{sender}/index.md` | medium |
| B: recent_activity | `activity_log/` + shared channels | trusted |
| C: related_knowledge | RAG vector search (knowledge + common_knowledge) | medium / untrusted |
| C0: important_knowledge | `[IMPORTANT]` tagged chunks | medium |
| E: pending_tasks | TaskStore + task results | trusted |
| F: episodes | RAG vector search (episodes/） | medium |

Additional injection:

| Item | Source | trust |
|------|--------|-------|
| Recent outbound | activity_log (up to 3 items, `channel_post` / `message_sent`) | trusted |
| Pending human notifications | `human_notify` events | trusted |

Skill and procedure bodies are not injected during Priming. Paths shown in the system prompt's skill catalog (e.g., `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`) are loaded via `read_memory_file`.

---

## Channel A: sender_profile

Injects the sender's user profile.

- **Source**: Read `shared/users/{sender}/index.md` directly
- **Limit**: `min(400, max_tokens // 4)`
- **When sender is unknown**: Skip

---

## Channel B: recent_activity

Injects a recent activity timeline.

- **Source**: `activity_log/{date}.jsonl` + the latest posts in shared channels

**Difference between Priming injection and explicit search**: Channel B provides compact background recall for heartbeat / inbox / cron, retrieving within the shared configuration limits. Use `search_memory(scope="activity_log")` to broadly search past activity logs by keyword. Injection and tool search are separate paths.

### Trigger-specific filtering

| Trigger | Excluded event types |
|---------|----------------------|
| `heartbeat` / `cron` / `inbox` / `task` | `tool_use`, `tool_result`, `heartbeat_start`, `heartbeat_reflection`, `inbox_processing_start`, `inbox_processing_end` |
| Others | `tool_use`, `tool_result`, `memory_write`, `cron_executed`, `heartbeat_start`, `heartbeat_end`, `heartbeat_reflection`, `inbox_processing_start`, `inbox_processing_end` |

---

## Channel C: related_knowledge

Injects related knowledge via RAG vector search.

- **Search method**: Dual-query (message context + keywords only)
- **Search targets**: Personal `knowledge/` + `shared_common_knowledge` collections
- **Minimum score**: `config.json` of `rag.min_retrieval_score` (default 0.3)

### trust separation

Search results are separated by trust level based on the chunk's `origin`:

| trust | Target | Handling |
|-------|------|------|
| `medium` | Personal knowledge, common_knowledge | Consumes budget with priority |
| `untrusted` | From external platforms (includes `external_platform` in `origin_chain`) | Injected with remaining budget. Tagged with `origin=ORIGIN_EXTERNAL_PLATFORM` |

---

## Channel C0: important_knowledge

Injects summary pointers for `[IMPORTANT]` tagged chunks.

- **Target**: `[IMPORTANT]` tagged chunks within `knowledge/`
- **Injection format**: Summary pointers. Details are retrieved via `read_memory_file`
- **Purpose**: Recall of important business rules and decision criteria

---

## Channel E: pending_tasks

Injects a summary of the task queue.

- **Limit**: `min(500, max_tokens // 3)`
- **Source**: `TaskQueueManager.format_for_priming()`
- **Contents**:
  - List and summary of `pending` / `in_progress` tasks
  - 🔴 HIGH marker for human-created tasks
  - ⚠️ STALE marker for tasks with no update for 30+ minutes
  - Status of delegated tasks
  - Completed task results from `task_results/`

---

## Channel F: episodes

Injects related episodes via RAG vector search.

- **Search target**: `episodes/` collection
- **Minimum score**: Shared with Channel C (`rag.min_retrieval_score`)

---

## Budgets and configuration

There is no profile selection; Priming always uses the compact retrieval path. `priming.max_tokens` is the recall budget (default: 2000), and `priming.channel_timeout_seconds` is the per-channel retrieval timeout (default: 60 seconds). `compact_background_recall` is a shared set of limits for heartbeat / inbox / cron, and they can all be disabled together with `compact_background_recall_enabled`.

- A (sender) is limited by `min(400, max_tokens // 4)`, and E (task) by `min(500, max_tokens // 3)`. Recent sends are limited to 3 items and 250 tokens.
- C (related knowledge) is retrieved when there is a chat/task trigger or question/request/delegation intent, and a message is present.
- B (recent activity) is retrieved within the configured limits for heartbeat / inbox / cron. F (episodes) is retrieved within the configured limits when the same trigger is present, a message is available, and related retrieval is enabled.
- Pending human notifications are handled separately from the recall budget.

---

## Hebbian LTP (Long-Term Potentiation)

Chunks searched and displayed during Priming have a lightweight search record updated via `record_access(kind="retrieved")`. Explicit use through `read_memory_file` or outcome reports is recorded as `used`, and forgetting protection is based on this explicit use.
