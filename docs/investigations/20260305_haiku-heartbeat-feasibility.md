# Haiku Heartbeat Feasibility & Multi-Tier Model Analysis

**Date:** 2026-03-05  
**Scope:** AnimaWorks heartbeats, cost comparison, operational complexity

---

## 1. Haiku Feasibility Assessment for Heartbeat

### Heartbeat System Prompt Contents (trigger="heartbeat")

From `core/prompt/builder.py`, when `trigger="heartbeat"`:

- **Group 1:** environment.md, behavior_rules, tool_data_interpretation
- **Group 2:** identity, injection (NO bootstrap, vision, specialty, emotion, a_reflection)
- **Group 3:** state (current_task + pending), org_context, messaging (truncated to 500 chars for background)
- **Priming:** 200-token budget (or dynamic: 5% of context_window when `priming.dynamic_budget=true`)
- **Heartbeat-specific:** heartbeat.md, heartbeat_default_checklist, heartbeat_history, heartbeat_subordinate_check, builder/heartbeat_tool_instruction
- **Supervisor tools:** delegate_task, read_subordinate_state, org_dashboard, etc. (if `_has_subordinates()`)

**Estimated system prompt size:** ~8,000–12,000 tokens (base) + priming + state.  
**Haiku context window:** 200K tokens. Sufficient headroom.

### Capability Check

| Capability | Haiku Support | Notes |
|-----------|---------------|-------|
| Tool use (search_memory, read_channel, send_message, delegate_task) | YES | Mode S (Agent SDK) or Mode A (LiteLLM); `claude-*` → S |
| Supervisor tools | YES | Same schema; Haiku can call delegate_task, etc. |
| Multi-step Observe/Plan/Reflect (20-step limit) | CAUTION | Soft prompt constraint. Haiku has weaker reasoning; may miss edge cases or produce less nuanced reflections |

### Budget Models in Codebase

From `core/config/models.py` `DEFAULT_MODEL_MODE_PATTERNS` and `KNOWN_MODELS`:
- `claude-haiku-4-5-20251001` is listed as Mode S ("軽量・高速")
- No explicit "budget" tier; Haiku is the low-cost Claude option

### Verdict

**YES, with caveats.**

- **Feasible for:** Leaf animas, simple checklists, low-stakes follow-ups
- **Not recommended for:** Top-level managers with many subordinates, complex delegation chains, animas requiring high-quality strategic reflection

---

## 2. Cost Comparison Table

### Pricing (USD per 1M tokens, from `core/memory/token_usage.py`)

| Model | Input | Output |
|-------|-------|--------|
| claude-opus-4-6 | $15.00 | $75.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4 | $0.80 | $4.00 |

### Per-Session Cost (typical heartbeat: 15k in, 5k out tokens)

| Model | Cost/session |
|-------|--------------|
| claude-opus-4-6 | $0.60 |
| claude-sonnet-4-6 | $0.12 |
| claude-haiku-4 | $0.032 |

### Daily Cost (200 heartbeats)

| Model | Cost/day |
|-------|----------|
| claude-opus-4-6 | $120.00 |
| claude-sonnet-4-6 | $24.00 |
| claude-haiku-4 | $6.40 |

### Observed 24h (from token_usage logs)

- Heartbeat sessions: ~500–1000 (varies by deployment)
- Current mix (Opus/Sonnet): ~$400–1500/24h
- If all heartbeats used Haiku: ~$30–50/24h (≈95% savings)

---

## 3. Multi-Tier Complexity Assessment

### Current State

- **1 model per anima** (`status.json` `model` field)
- Same model used for chat, heartbeat, cron, inbox, task
- Fallback: `fallback_model` in status.json (single fallback chain for API failures)

### Proposed: 2 Tiers (chat + heartbeat)

| Aspect | Assessment |
|--------|------------|
| Schema | Add optional `heartbeat_model` to status.json |
| Resolution | When `trigger=="heartbeat"`, use `heartbeat_model` if set, else `model` |
| Code touch points | ~5–10 (load_model_config, resolve_anima_config, executor invocation) |
| Complexity | **LOW** |

### Proposed: 3 Tiers (chat + heartbeat + cron)

| Aspect | Assessment |
|--------|------------|
| Schema | Add `heartbeat_model`, `cron_model` |
| Cron frequency | Lower than heartbeat; cost impact smaller |
| Complexity | **MEDIUM** |

### CLI Design

```
animaworks anima set-model <name> <model> [--for heartbeat|cron]
```

- Current `set-model` updates `model` only
- `--for heartbeat` would set `heartbeat_model`
- Animas could "self-configure" only if we add a `set_model` tool (not currently available)

### Fallback Chain

- **Option A:** If `heartbeat_model` fails (rate limit, timeout), retry with main `model`
- **Option B:** No fallback; fail and retry next cycle
- **Recommendation:** Option A (reuse existing `fallback_model` logic where applicable)

---

## 4. Recommendation

### Tier Count

**Support 2 tiers (chat + heartbeat).**

- 3 tiers add complexity for marginal gain; cron runs less frequently
- 2 tiers give clear cost benefit for heartbeat-heavy workloads

### Implementation Outline

1. Add `heartbeat_model` (optional) to status.json schema
2. In `load_model_config` / `resolve_anima_config`: when building ModelConfig for heartbeat trigger, use `heartbeat_model` if set
3. CLI: `animaworks anima set-model <name> <model> [--for heartbeat]`
4. Fallback: if heartbeat_model fails, retry with main model

### Pilot Plan

1. Start with 2–3 leaf animas on Haiku for heartbeat
2. Monitor: HEARTBEAT_OK rate, follow-up quality, reflection quality
3. Expand if metrics are acceptable

---

## Appendix: Files Referenced

- `core/prompt/builder.py` — system prompt construction, trigger filtering
- `core/memory/token_usage.py` — DEFAULT_PRICING
- `core/config/models.py` — DEFAULT_MODEL_MODE_PATTERNS, KNOWN_MODELS
- `templates/en/prompts/heartbeat.md`, `builder/heartbeat_tool_instruction.md`
- `scripts/analyze_heartbeat_tokens.py` — token usage analysis
