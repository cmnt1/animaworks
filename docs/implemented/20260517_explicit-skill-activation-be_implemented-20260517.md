---
title: "Explicit Skill Activation BE — thread-scoped active skill execution"
status: ready
created: 2026-05-17
series: hermes-integration
priority: high
---

# Explicit Skill Activation BE — 明示的に発動したスキルを thread 単位で prompt に注入する

## Overview

Hermes Agent から取り込んだ skill ecosystem は、AnimaWorks では catalog / pointer / `read_memory_file` を中心に動いている。次の段階として、UI から選択されたスキルを BE 側で「明示的に有効化済み」として保持し、チャット実行時に本文を system prompt へ注入する。

今回の実装は BE のみを対象とし、UI は後続作業とする。UI が後から薄く実装できるよう、API と thread-scoped state を先に確定する。

## Problem / Background

### Current State

- Skill catalog は `build_system_prompt()` Group 4 で提示されるが、本文は通常注入されない。`core/prompt/builder.py:590`
- `read_memory_file` で SKILL.md を読むと usage は `view` として記録されるが、「この会話でこのスキルを使う」という active state はない。`core/tooling/handler_memory.py:520`
- cron は `skills:` 参照を本文注入し、`use` を記録する専用経路を持つ。`core/skills/cron_context.py:70`
- `SkillUsageTracker` には `use` / `success` / `failure` event type があるが、通常チャットで明示発動を記録する標準経路がない。`core/skills/usage.py:17`

### Root Cause

1. Active skill の状態モデルがない — `core/prompt/builder.py:738`
2. Prompt builder の入力に thread-local active skill context がない — `core/_agent_cycle.py:266`
3. UI が操作できる active skill API がない — `server/routes/__init__.py:31`
4. 通常チャットで skill body を「使う」ための安全判定・サイズ制限・usage 記録が cron 専用実装に閉じている — `core/skills/cron_context.py:70`

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/prompt/builder.py` | Direct | active skill 本文を system prompt に注入する場所 |
| `core/_agent_cycle.py` | Direct | `thread_id` を prompt builder に渡す必要がある |
| `core/skills/activation.py` | Direct | 新規 active skill state / render / safety API |
| `server/routes/skills.py` | Direct | UI 用 API の追加 |
| `core/skills/usage.py` | Indirect | `use` event を明示発動時に記録 |
| `core/skills/cron_context.py` | Indirect | 安全判定・truncation の既存方針を踏襲 |

## Decided Approach / 確定方針

### Design Decision

確定: BE に `ActiveSkill` 層を追加し、active skill は `anima + thread_id` 単位で `state/active_skills.json` に保存する。チャット実行時は active skill 本文を `## Active Skills` として system prompt に注入し、catalog の候補表示とは別扱いにする。これにより UI は後続で `GET/PUT /api/animas/{name}/skills/active` を操作するだけで明示的スキル発動を実現できる。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| ChatRequest に毎回 `skill_refs` を渡す | API 呼び出し単体で完結する | UI が選択状態を保持し続ける必要があり、streaming / non-streaming / resume で挙動がばらける | Rejected: thread conversation state と整合しない |
| slash command を先に実装する | Hermes の `/skill-name` に近い | UI / 入力解析 / command routing が先行し、BE の契約が曖昧になる | Rejected: 今回は BE 基盤を先に固定する |
| `read_memory_file` の view を use とみなす | 実装が最小 | 読んだだけか、実行方針として有効化したかを区別できない | Rejected: usage metrics が歪む |
| cron context builder をそのまま流用する | 既存 code reuse が多い | `Cron Skills` 表示・cron config 名・notes が chat 用 active skill とずれる | Rejected: 共通方針は踏襲しつつ chat 用 builder を分ける |

### Key Decisions from Discussion

1. **Active skill は thread 単位**: `thread_id` ごとに有効化状態を保持する — Reason: 会話スレッドごとの意図に一致し、session/preload に近い。
2. **解除されるまで有効**: one-turn ではなく、UI が明示解除するまで残す — Reason: UI 側が active badge / toggle として扱いやすい。
3. **本文注入は catalog とは別**: `## Active Skills` に body を入れる — Reason: 候補ではなく発動済みであることを LLM に明確化する。
4. **usage は注入時に `use` 記録**: API 設定時ではなく prompt render 時に記録する — Reason: 実際にモデルへ渡ったものだけを利用実績にする。
5. **安全判定は BE で完結**: `dangerous` / `blocked` / `quarantine` は拒否、`warn` / `caution` / risky skill は `confirm_risk=true` なしでは拒否する — Reason: UI 実装前でも安全境界を保つ。

### Changes by Module

| Module | Change Type | Description |
|--------|-------------|-------------|
| `core/skills/activation.py` | New | active skill state, validation, resolve, render, API response helpers |
| `core/prompt/builder.py` | Modify | `thread_id` 引数を受け取り、chat prompt の Group 4 に active skill context を追加 |
| `core/_agent_cycle.py` | Modify | blocking / streaming / retry prompt build へ `thread_id` を渡す |
| `server/routes/skills.py` | New | skill catalog / active skill API を提供 |
| `server/routes/__init__.py` | Modify | skills router を `/api` に登録 |
| `docs/api-reference.md` | Modify | English API docs を追記 |
| `docs/api-reference.ja.md` | Modify | Japanese API docs を追記 |
| `tests/unit/test_skill_activation.py` | New | active skill state / safety / render tests |
| `tests/unit/server/routes/test_skills.py` | New | FastAPI route tests |
| `tests/e2e/test_explicit_skill_activation_e2e.py` | New | prompt injection integration tests |

### Edge Cases

| Case | Handling |
|------|----------|
| Missing ref | `rejected: [{"ref": "...", "reason": "not_found"}]` |
| Duplicate refs | Keep first occurrence and preserve order |
| Invalid `thread_id` | API returns 400; core raises `ValueError` |
| Deleted skill remains in state | Prompt render skips it and reports rejection in API reads |
| `dangerous` / `blocked` / `quarantine` | Always reject |
| `warn` / `caution` | Reject unless `confirm_risk=true`; accepted response includes warning |
| `risk.destructive` / `risk.external_send` / `risk.requires_human_approval` | Reject unless `confirm_risk=true`; accepted response includes warning |
| Body exceeds per-skill limit | Attach heading and path, omit body with `reason: max_skill_chars_exceeded` |
| Total active skill body exceeds limit | Later skills are attached as omitted body with `reason: max_total_chars_exceeded` |
| Non-chat trigger | Do not inject active skills into heartbeat / cron / inbox / task prompts |

## Implementation Plan

### Phase 1: Core Active Skill Layer

| # | Task | Target |
|---|------|--------|
| 1-1 | Add dataclasses / helpers for active skill state and results | `core/skills/activation.py` |
| 1-2 | Persist state at `state/active_skills.json` keyed by thread id | `core/skills/activation.py` |
| 1-3 | Resolve refs via `SkillIndex.resolve_skill_reference()` and apply access policy | `core/skills/activation.py` |
| 1-4 | Render accepted skills as `## Active Skills` with truncation | `core/skills/activation.py` |
| 1-5 | Record `SkillUsageEventType.use` only when rendered into prompt | `core/skills/activation.py` |

**Completion condition**: Core tests can set active refs, reject unsafe refs, render body, and record `use` events.

### Phase 2: Prompt Integration

| # | Task | Target |
|---|------|--------|
| 2-1 | Add `thread_id` argument to `build_system_prompt()` | `core/prompt/builder.py` |
| 2-2 | Inject active skill context in Group 4 for chat prompts only | `core/prompt/builder.py` |
| 2-3 | Pass `thread_id` from blocking and streaming cycle paths | `core/_agent_cycle.py` |
| 2-4 | Keep existing catalog and cron behavior unchanged | `core/prompt/builder.py`, `core/skills/cron_context.py` |

**Completion condition**: Chat prompt includes active skill body for the selected thread and excludes it for other threads / background triggers.

### Phase 3: Server API

| # | Task | Target |
|---|------|--------|
| 3-1 | Add `GET /api/animas/{name}/skills` | `server/routes/skills.py` |
| 3-2 | Add `GET /api/animas/{name}/skills/active` | `server/routes/skills.py` |
| 3-3 | Add `PUT /api/animas/{name}/skills/active` | `server/routes/skills.py` |
| 3-4 | Register router | `server/routes/__init__.py` |

**Completion condition**: UI-compatible API can list, set, read, and clear active skills.

### Phase 4: Tests and Docs

| # | Task | Target |
|---|------|--------|
| 4-1 | Add unit tests for activation core | `tests/unit/test_skill_activation.py` |
| 4-2 | Add server route tests | `tests/unit/server/routes/test_skills.py` |
| 4-3 | Add prompt e2e test | `tests/e2e/test_explicit_skill_activation_e2e.py` |
| 4-4 | Document API | `docs/api-reference.md`, `docs/api-reference.ja.md` |

**Completion condition**: New tests and existing skill tests pass.

## Scope

### In Scope

- Thread-scoped active skill state.
- BE APIs for list / active get / active set.
- Prompt injection for chat active skills.
- Safety rejection and warnings.
- Usage `use` recording on prompt render.
- Unit and E2E coverage for BE behavior.

### Out of Scope

- UI picker / active badge / risk confirmation dialog — Reason: BE contract must land first.
- Slash command parsing such as `/skill-name` — Reason: command UX should be a follow-up after API stabilization.
- Supporting file discovery for `references/`, `scripts/`, `assets/` — Reason: separate Hermes compatibility enhancement.
- Outcome reporting `success` / `failure` for active skills — Reason: requires agent/tool completion semantics design.
- Importing the full Hermes bundled skill corpus — Reason: migration/library scope, unrelated to active execution state.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Prompt grows too large | Chat requests can exceed context budget | Apply per-skill and total char limits before prompt assembly |
| Unsafe skill body becomes active | Destructive/external-send instructions could be over-privileged | Reject blocked/quarantine/dangerous and require `confirm_risk` for warn/caution/risky |
| Persistent active state surprises user | A skill remains active longer than expected | Keep state thread-scoped and expose explicit clear via `refs: []` |
| Usage overcounting | Repeated prompt builds increment `use` too often | Accept this as "model received active skill" metric for now; do not count API set |
| Existing prompt tests break | Signature changes may affect callers | Add default `thread_id="default"` and update direct cycle calls |

## Acceptance Criteria

- [ ] `GET /api/animas/{name}/skills` returns visible skills with `active` status for `thread_id`.
- [ ] `PUT /api/animas/{name}/skills/active` sets accepted active refs and returns rejected refs with reasons.
- [ ] `PUT /api/animas/{name}/skills/active` with `refs: []` clears the thread's active skills.
- [ ] Active skill body is injected into chat system prompt under `## Active Skills`.
- [ ] Active skill body is not injected into heartbeat / cron / inbox / task prompts.
- [ ] Active skill state is isolated by `thread_id`.
- [ ] Rendering active skills records `SkillUsageEventType.use`.
- [ ] `dangerous`, `blocked`, and `quarantine` skills are rejected.
- [ ] `warn`, `caution`, and risky skills require `confirm_risk=true`.
- [ ] New unit, server route, and prompt e2e tests pass.
- [ ] Existing skill catalog and skill-backed cron tests still pass.

## References

- `core/skills/models.py:17` — Skill usage event types include `use`.
- `core/skills/index.py:72` — Skill discovery and reference resolution.
- `core/skills/loader.py:105` — Skill access decision and body loading.
- `core/skills/cron_context.py:70` — Existing explicit skill body injection path for cron.
- `core/prompt/builder.py:590` — Current skill catalog prompt insertion.
- `core/_agent_cycle.py:266` — Blocking prompt build path.
- `core/_agent_cycle.py:876` — Streaming prompt build path.
- `server/routes/chat_models.py:24` — Chat request has `thread_id`.
- `server/routes/__init__.py:31` — API router registration point.
