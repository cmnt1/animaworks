# Machine Tool — Design Philosophy

## The Craftsperson and Machine Tool Principle

An Anima is a craftsperson (master artisan). External agent CLIs invoked through `machine_run` are machine tools.

Machine tools deliver extraordinary work capability as extensions of the craftsperson's hands, but they are NOT craftspeople.

- Machine tools do NOT decide what to build (no autonomy)
- Machine tools do NOT remember yesterday's work (no memory)
- Machine tools do NOT talk to other craftspeople (no relationships)
- Machine tools do NOT know what they are (no identity)
- Machine tools do NOT show up tomorrow (no persistence)

**Tools extend capability. They don't replicate existence.**

## Why Animas and Machine Tools Are Different

| Attribute | Anima (Craftsperson) | machine (Machine Tool) |
|-----------|---------------------|----------------------|
| Identity | Has (identity.md) | None |
| Memory | Accumulates (episodes, knowledge) | Resets every time |
| Autonomy | Has (heartbeat, cron) | None (invoked only) |
| Relationships | Has (supervisor, peers, subordinates) | None |
| Judgment | Makes decisions (what to do / not do) | None (follows instructions only) |
| Growth | Grows (consolidation, learning) | None |
| Org membership | Has (org tree) | None |

## Usage Principles

### 1. Instructions Are Blueprints

The `instruction` you give a machine tool should be as specific and detailed as a blueprint drawn by a craftsperson.

**Good example:**
```
Refactor the following module:
- Target: core/tools/web_search.py
- Goal: Migrate from httpx to aiohttp
- Constraint: Do not change existing interfaces (search(), format_results())
- Coding conventions: Google-style docstring, from __future__ import annotations
- Tests: Existing tests tests/unit/core/tools/test_web_search.py must pass
```

**Bad example:**
```
Fix web_search
```

### 2. Output Is Raw Material

Machine tool output is "raw material", not a "finished product". You (the craftsperson) must verify and contextualize it before it becomes a result.

- Do not blindly trust the output
- Verify quality before integrating into memory
- If there are issues, improve instructions and re-run

### 3. Memory Integration Is the Craftsperson's Job

"Techniques that worked" and "patterns that failed" are written into memory by YOU. Machine tools remember nothing.

### 4. Reporting Is the Craftsperson's Responsibility

Reporting machine tool results to your supervisor is YOUR duty. Machine tools talk to nobody.

## Available Engines

| Engine | Features | Best For |
|--------|----------|----------|
| `claude` | Claude CLI. Rich tools. High quality | Code implementation, refactoring, docs |
| `codex` | Codex CLI. Native sandbox | File operations requiring safety |
| `gemini` | Gemini CLI. Google AI | Exploration, analysis |
| `cursor-agent` | Cursor Agent. IDE integration | Code implementation, workspace ops |

## Limitations

- Maximum 5 calls per session, 2 per heartbeat
- Sync timeout: 600 seconds, async: 1800 seconds
- Machine tools cannot access AnimaWorks infrastructure (memory, messaging, org)
- Environment variables are sanitized; only API keys are forwarded
