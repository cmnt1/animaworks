---
gh_issue_number: N/A
status: ready_for_implementation
created_at: 2026-05-11
---

# Rin Session Compression and Context Isolation — Prevent Chat From Starting With Repeated Compression

## Overview

Rin's 2026-05-11 17:27 JST chat started with framework-side conversation compression because idle compaction had fired but LLM compression failed and raw turns stayed above the 50-turn trigger. The same incident also exposed Mode C session contamination: inbox/background runs share chat short-term memory and Codex thread state, while Codex cumulative token usage is treated as live context occupancy.

This issue fixes the full path so human chat is the only persistent chat session, idle compaction outcomes are auditable, compression has deterministic fallback behavior, and Codex token usage no longer produces false context-overflow short-term saves.

## Problem / Background

### Current State

- `ConversationMemory.needs_compression()` returns true once raw turns exceed 50, and `process_message_stream()` emits `compression_start` before answering.
- Idle compaction ran for rin on 2026-05-11 but `qwen3.6-27b` compression failed with "No deployments available"; raw turns stayed above threshold.
- `idle_compaction` activity was logged as success although conversation compression and finalization failed.
- Mode C Codex uses `chat` session state for `inbox:*`; inbox can read, clear, and overwrite chat short-term memory.
- Codex `turn.completed` usage is divided by the context window. On 2026-05-11 17:27, `(1,047,486 + 6,117) / 272,000 = 387.4%`, even though the prompt was only 122,327 bytes.
- Codex `num_turns` is usually absent, so `turn_count` is saved as 0.

### Root Cause

1. Compression has no active-model fallback and no deterministic fallback. `core/memory/conversation_compression.py:51`, `core/memory/conversation_compression.py:162`
2. Idle compaction discards failure details and logs success when Mode C routine completes. `core/session_compactor.py:362`, `core/session_compactor.py:450`
3. Mode C Codex session type maps everything except heartbeat/cron to `chat`; `inbox:*` is not isolated. `core/execution/codex_sdk.py:183`
4. `run_cycle_streaming()` always uses `ShortTermMemory(... session_type="chat")`, injects it for non-heartbeat triggers, and clears it on success. `core/_agent_cycle.py:678`, `core/_agent_cycle.py:718`, `core/_agent_cycle.py:1017`
5. Codex cumulative usage is used as context usage. `core/execution/codex_sdk.py:1363`, `core/prompt/context.py:281`
6. Codex adapter defaults missing `num_turns` to 0. `core/execution/codex_sdk.py:432`
7. Inbox activity metadata does not make inbox grouping unambiguous for conversation views/history. `core/_anima_inbox.py:524`, `core/memory/_activity_conversation.py:197`

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| Human chat UX | Direct | Chat can begin with repeated `compression_start` after failed idle compression. |
| Conversation memory | Direct | Raw turn count remains above 50 when compression LLM is unavailable. |
| Short-term memory | Direct | Inbox/background runs can consume and clear chat short-term state. |
| Codex thread persistence | Direct | Inbox can resume and bloat the same persisted Codex thread used for human chat. |
| Context tracking | Direct | Cumulative token usage produces impossible 387%/1525% context ratios. |
| Activity logs | Indirect | `idle_compaction` success hides partial failures. |

## Decided Approach / 確定方針

### Design Decision

確定: split human chat from inbox/background session state, add active-model and deterministic compression fallback, and make Codex context threshold decisions use prompt-sized estimates instead of cumulative billing usage. This directly satisfies the user requirement that only human chat is session-targeted, inbox does not mix into user conversation, idle compaction remains auditable, and Claude Code native compaction is not used for normal token management.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Keep raw turns when compression LLM fails | Simple | Repeats `compression_start` on every later chat and leaves the 50-turn trigger unresolved | Rejected: this is the observed failure mode |
| Call Claude Code native `/compact` | Existing external behavior | Violates the requirement to avoid Claude Code compression as the primary token-management mechanism | Rejected: requirement conflict |
| Let inbox reuse chat session state | Less code | Causes user chat contamination and short-term memory loss | Rejected: violates human-chat-only session boundary |
| Use Codex cumulative usage as context occupancy | Easy to log | Produces false ratios above 100% and unnecessary short-term saves | Rejected: not a reliable context signal |
| Disable context tracking entirely for Mode C | Avoids false positives | Removes a useful safety check for truly oversized prompts | Rejected: prompt-sized estimate remains useful |

### Key Decisions from Discussion

1. **Compression model fallback**: If the configured compression/consolidation model fails, retry with the active anima model and credential. Reason: the active model is already configured to work for the current anima.
2. **Deterministic fallback**: If both LLM calls fail, archive older turns and write an extractive fallback summary while keeping recent turns. Reason: raw turn count must drop below the compression trigger even during model outages.
3. **Log partial failures**: Idle compaction must record compression status and finalization status in activity log metadata. Reason: success currently masks the relevant failure.
4. **Human chat session boundary**: Only `message:*` triggers use persistent `shortterm/chat` and resumable Codex chat thread IDs. Reason: inbox/heartbeat/cron/task are background work, not user conversation sessions.
5. **Codex context accounting**: Keep Codex usage in token_usage logs, but do not use cumulative usage to trigger short-term memory saves. Reason: usage is a billing/cumulative measure, not current context occupancy.
6. **Turn count correction**: Codex result messages must report at least one turn when a turn completed. Reason: `turn_count=0` hides completed work and makes logs misleading.

### Changes by Module

| Module | Change Type | Description |
|--------|-------------|-------------|
| `core/memory/_llm_utils.py` | Modify | Add helper for one-shot completion with explicit model config/credential so active model fallback can reuse current anima settings. |
| `core/memory/conversation_compression.py` | Modify | Retry compression with active model, then deterministic extractive fallback; return detailed compression result instead of only bool. |
| `core/memory/conversation.py` | Modify | Preserve backward-compatible `compress_if_needed()` bool API and expose detailed result for compactor/logging. |
| `core/session_compactor.py` | Modify | Log `conversation_compression_status`, `fallback_used`, `finalize_status`, and `raw_turns_after` in `idle_compaction` activity metadata. |
| `core/_agent_cycle.py` | Modify | Resolve session type from trigger; inject/clear chat shortterm only for `message:*`; clear Mode C chat thread when threshold save happens for chat. |
| `core/execution/codex_sdk.py` | Modify | Separate Codex session type resolution for inbox/cron/task; use chat thread id paths correctly; do not feed cumulative usage into `ContextTracker`; set completed turn count. |
| `core/_anima_inbox.py` | Modify | Pass inbox session type or inbox thread id to run cycle, and log inbox metadata with `session_type`, `trigger`, and batch/thread id. |
| `core/memory/_activity_conversation.py` | Modify | Exclude non-chat channel entries from default human chat history/grouping. |
| `tests/unit/` | Modify | Add focused unit tests for compression fallback, idle logging, shortterm routing, Codex context accounting, and inbox activity filtering. |
| `tests/e2e/` | Modify | Add integration test covering human chat shortterm preservation across inbox execution. |

### Edge Cases

| Case | Handling |
|------|----------|
| Compression LLM returns empty text | Treat as failure and continue to active-model fallback. |
| Active model is a Codex model | Use the existing Codex one-shot fallback path; if unsupported, deterministic fallback runs. |
| Deterministic fallback runs on very large turns | Store bounded excerpts and timestamps, keep recent display turns, and increment `compressed_turn_count` by archived count. |
| Idle compaction has no turns to summarize | Log status `skipped_no_compression_needed` and keep existing shortterm behavior. |
| Inbox has pending work while chat shortterm exists | Inbox does not inject or clear `shortterm/chat`; it uses isolated `shortterm/inbox` only when a future caller explicitly opts into inbox shortterm. |
| Codex usage exceeds model window | Token usage is logged; context threshold is not tripped unless prompt estimate exceeds threshold. |
| Human chat threshold is exceeded by prompt estimate | Save chat shortterm and clear persisted chat Codex thread id. |
| Existing legacy shortterm files exist under root | Keep existing migration behavior for `session_type="chat"`; do not migrate them into inbox. |

## Implementation Plan

### Phase 1: Compression fallback and audit logging

| # | Task | Target |
|---|------|--------|
| 1-1 | Introduce compression result dataclass with statuses: `skipped`, `llm_primary`, `llm_active_model`, `deterministic_fallback`, `failed`. | `core/memory/conversation_compression.py` |
| 1-2 | Add active-model fallback call using current `ModelConfig`. | `core/memory/_llm_utils.py`, `core/memory/conversation_compression.py` |
| 1-3 | Add deterministic extractive fallback that reduces raw turns below `_MAX_TURNS_BEFORE_COMPRESS`. | `core/memory/conversation_compression.py` |
| 1-4 | Add detailed idle compaction activity metadata. | `core/session_compactor.py` |

**Completion condition**: compression failure cannot leave more than 50 raw turns after `compress_if_needed()` when there are enough turns to compress.

### Phase 2: Session isolation

| # | Task | Target |
|---|------|--------|
| 2-1 | Add shared trigger-to-session-type helper for `message`, `inbox`, `heartbeat`, `cron`, `task`, and `consolidation`. | `core/_agent_cycle.py` or new small helper module |
| 2-2 | Use chat shortterm only for `message:*` triggers. | `core/_agent_cycle.py` |
| 2-3 | Make Mode C Codex thread persistence use chat only for `message:*`; background triggers start fresh and are not saved as chat. | `core/execution/codex_sdk.py` |
| 2-4 | Ensure inbox passes or logs an inbox-specific session/thread id. | `core/_anima_inbox.py` |
| 2-5 | Filter default human chat history to `channel=="chat"` entries. | `core/memory/_activity_conversation.py` |

**Completion condition**: running inbox after chat shortterm exists leaves `shortterm/chat/session_state.json` untouched.

### Phase 3: Codex context accounting and turn count

| # | Task | Target |
|---|------|--------|
| 3-1 | Stop updating `ContextTracker` with Codex cumulative usage. | `core/execution/codex_sdk.py` |
| 3-2 | Add prompt-estimate update path for Mode C using system prompt + prompt byte/char estimate. | `core/_agent_cycle.py` or `core/prompt/context.py` |
| 3-3 | Track completed Codex turns and set `CodexResultMessage.num_turns >= 1` after `turn.completed`. | `core/execution/codex_sdk.py` |

**Completion condition**: large Codex token_usage values alone do not create `context_usage_ratio > 1.0` or save shortterm.

### Phase 4: Tests

| # | Task | Target |
|---|------|--------|
| 4-1 | Unit-test deterministic compression fallback and active-model fallback order. | `tests/unit/core/memory/` |
| 4-2 | Unit-test idle compaction metadata for success and fallback. | `tests/unit/test_session_compactor.py` |
| 4-3 | Unit-test shortterm routing for `message:*` and `inbox:*`. | `tests/unit/core/` |
| 4-4 | Unit-test Codex cumulative usage does not trip context threshold. | `tests/unit/test_codex_sdk_executor.py` |
| 4-5 | E2E-test chat shortterm survives inbox execution. | `tests/e2e/` |

**Completion condition**: focused tests and relevant existing tests pass.

## Scope

### In Scope

- Conversation compression fallback behavior.
- Idle compaction activity logging.
- Human chat/inbox/background session isolation for shortterm and Codex thread persistence.
- Codex Mode C context accounting correction.
- Activity log metadata and human chat filtering.
- Unit and E2E tests for the above.

### Out of Scope

- Changing Claude Code native compact behavior beyond ensuring it is not used for this flow.
- Reworking all memory consolidation jobs.
- Replacing Codex SDK or changing model configuration defaults globally.
- Migrating historical activity logs.
- Recomputing existing `token_usage` files.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Background runs lose useful shortterm continuity | Inbox may not resume prior background work | Keep background prompts self-contained; do not route background through chat shortterm. |
| Deterministic summary is lower quality than LLM summary | Older nuance can be compressed less well during outage | Preserve timestamps, speakers, bounded excerpts, and `compressed_turn_count`; retry LLM compression on future turns. |
| Tests depend on private helper names | Refactor friction | Prefer public methods where available; keep helper tests narrowly scoped when behavior is internal. |
| Session type routing changes Codex resume behavior | Existing background resume assumptions may change | Requirement says human chat only is session-targeted; add tests documenting this behavior. |

## Acceptance Criteria

- [ ] If the primary compression model fails, active model fallback is attempted and logged.
- [ ] If all LLM compression attempts fail, deterministic fallback reduces raw turns to `_MAX_DISPLAY_TURNS` and increments `compressed_turn_count`.
- [ ] Idle compaction activity metadata records compression status, fallback used, finalize status, and raw turn count after compaction.
- [ ] `inbox:*` does not inject, clear, or overwrite `shortterm/chat/session_state.json`.
- [ ] `inbox:*`, `heartbeat`, `cron:*`, and `task:*` do not resume or persist the human chat Codex thread id.
- [ ] Human chat still uses persistent chat shortterm and Codex thread id.
- [ ] Codex cumulative usage is still written to `token_usage`.
- [ ] Codex cumulative usage alone does not mark context threshold exceeded.
- [ ] Codex completed turns are not reported as `turn_count=0`.
- [ ] Default human conversation history excludes inbox entries unless explicitly requested.
- [ ] Focused unit tests pass.
- [ ] Relevant E2E/integration test passes.

## References

- `core/_anima_messaging.py:541` — pre-chat compression start path.
- `core/memory/conversation_compression.py:98` — compression threshold check.
- `core/memory/conversation_models.py:56` — 50-turn compression trigger.
- `core/session_compactor.py:362` — Mode C idle compaction path.
- `core/execution/codex_sdk.py:183` — Mode C session type resolution.
- `core/execution/codex_sdk.py:1363` — Codex usage handling.
- `core/_agent_cycle.py:678` — streaming shortterm initialization.
- `core/_agent_cycle.py:718` — shortterm injection.
- `core/_agent_cycle.py:982` — streaming threshold save path.
- `core/_anima_inbox.py:484` — inbox streaming run call.
- `core/memory/_activity_conversation.py:197` — default thread fallback.
- `/home/main/.animaworks/animas/rin/token_usage/2026-05-11.jsonl` — 17:27 token usage evidence.
- `/home/main/.animaworks/animas/rin/shortterm/chat/archive/20260511_173358.json` — 17:27 inbox shortterm evidence.
