# Fact Extraction Rollout Report - 2026-06-11

Related issue: #231, follow-up to #210.

## Scope

- Runtime data directory inspected: `~/.animaworks`
- Observation window available in local logs: 2026-06-04 through 2026-06-11
- Enabled Animas in `~/.animaworks/animas/*/status.json`: 27/27
- Global config: `rag.facts_extraction_enabled=true`, `rag.entity_registry_enabled=true`, `rag.facts_reconcile_enabled=true`
- Per-Anima overrides: no Anima disables fact extraction; all 27 inherit the global setting.

## Current Rollout State

All enabled Animas are configured to run legacy atomic fact extraction. The rollout is not a clean success window yet: the available runtime evidence shows extraction is being attempted, counters are now visible, and successful writes occur, but recent failures are dominated by LLM request timeouts.

Structured completion counters are present in the current logs:

| Metric | Value |
|---|---:|
| Completion log entries with `facts_extracted` / `facts_failed` | 18 |
| Completion entries with `facts_failed=0` | 4 |
| Completion entries with `facts_failed>0` | 14 |
| Facts extracted in structured completion logs | 47 |
| Current `facts/*.jsonl` lines on disk | 53 |
| Animas with current `facts/*.jsonl` files | 6 |
| Animas with extractor tracebacks in the 7-day log window | 21 |

Per-Anima structured counter snapshot:

| Anima | Runs | Facts extracted | Failed runs |
|---|---:|---:|---:|
| hina | 1 | 0 | 1 |
| kotoha | 1 | 0 | 1 |
| mei | 5 | 12 | 4 |
| mikoto | 1 | 0 | 1 |
| mio | 1 | 0 | 1 |
| nagi | 1 | 0 | 1 |
| natsume | 1 | 0 | 1 |
| ritsu | 1 | 10 | 0 |
| sae | 1 | 17 | 0 |
| sakura | 1 | 0 | 1 |
| sanae | 1 | 0 | 1 |
| shion | 1 | 8 | 0 |
| sumire | 1 | 0 | 1 |
| yuki | 1 | 0 | 1 |

Animas with stored fact files at inspection time:

| Anima | Fact files | Fact rows | Latest file |
|---|---:|---:|---|
| aoi | 1 | 3 | `2026-06-11.jsonl` |
| mei | 1 | 12 | `2026-06-11.jsonl` |
| ritsu | 1 | 10 | `2026-06-11.jsonl` |
| sae | 1 | 17 | `2026-06-11.jsonl` |
| sakura | 1 | 3 | `2026-06-10.jsonl` |
| shion | 1 | 8 | `2026-06-11.jsonl` |

## Failure Pattern

The dominant failure pattern is entity-extraction LLM timeout:

- Sampled logs show `openai.APITimeoutError: Request timed out`.
- LiteLLM reports `timeout value=30.0` with roughly 91 seconds total elapsed after retries.
- Local log search found 301 timeout-related lines in Anima logs during the available window.

This means the previous rollout had visibility gaps and timeout-driven extraction loss, not an indexing or fact-store write failure. Successful examples (`sae`, `ritsu`, `shion`, `mei`) wrote `facts/*.jsonl` and reindexed the facts scope.

## Mitigation Added In This Branch

- Added `rag.fact_extraction_timeout_seconds` to `RAGConfig`, default `120`.
- `_resolve_extraction_config()` now uses that global timeout before applying per-Anima `status.json` `extraction_timeout` overrides.
- The fact-reconciliation LLM helper uses the same default/global timeout path.
- Existing structured logs now expose `facts_extracted` and `facts_failed` for session and consolidation extraction paths.
- Unit coverage verifies success and failure counters and the configurable timeout path.

## Status

Recorded as a rollout verification report with visible failure rate. The code path is enabled for all 27 Animas, and successful fact extraction is confirmed, but the inspected runtime window is not a clean all-Anima success window. The timeout mitigation should be observed over the next 7-day runtime window before claiming zero-regression production health.
