# LoCoMo Event-Time Recall and Temporal Rerank — 最初の実装単位

## Overview

This issue implements the first child of `docs/issues/20260602_locomo-memory-score-improvement-parent.md`: event-time metadata propagation, retrieval-only recall diagnostics, and an opt-in temporal rerank ablation. The goal is to improve measurement and temporal retrieval quality without changing default smoke behavior or deepseek baseline thresholds.

Dependency: parent issue `docs/issues/20260602_locomo-memory-score-improvement-parent.md`.

## Problem / Background

### Current State

- LoCoMo Legacy `scope_all` smoke after rollback is overall F1 45.3%, but temporal is 47.4%, multi_hop is 21.4%, and open_domain is 38.4%.
- LoCoMo session timestamps exist in the dataset as strings such as `8:56 pm on 20 July, 2023`.
- `benchmarks/locomo/adapter.py:163` writes that timestamp into the session heading, but the indexed chunk metadata generally falls back to file mtime.
- `core/memory/rag/indexer.py:682` only recognizes `## HH:MM` headings for episode time chunking.
- `benchmarks/locomo/adapter.py:343` converts retrieved hits to pipeline items and drops `valid_at` / session fields.
- The benchmark runner only measures answer F1 after LLM calls, so retrieval recall cannot be measured quickly.

### Root Cause

1. **LoCoMo session heading is not parsed as event time** — `core/memory/rag/indexer.py:682` expects `## HH:MM`, while LoCoMo uses `## Session N - natural language datetime`.
2. **Metadata is not propagated into pipeline results** — `benchmarks/locomo/adapter.py:343` keeps only source, chunk index, memory type, and search method.
3. **No retrieval-only metric exists** — `benchmarks/locomo/runner.py:248` always proceeds to answer generation and token F1, making smoke slow and hiding retrieval failures.
4. **Temporal ranking cannot be safely evaluated** — `core/memory/retrieval/pipeline.py:66` merges candidates, then reranks, but there is no opt-in additive temporal scoring hook or diagnostic output.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/rag/indexer.py` | Direct | LoCoMo session timestamps are not stored as structured `valid_at` metadata. |
| `benchmarks/locomo/adapter.py` | Direct | Structured metadata is lost before RRF/rerank/gate and before result JSON. |
| `benchmarks/locomo/retrieval_diagnostics.py` | Direct | New module required for LLM-free recall measurement. |
| `core/memory/retrieval/pipeline.py` | Direct | Needs opt-in temporal boost hook that preserves default behavior. |
| `benchmarks/locomo/runner.py` | Indirect | Existing smoke remains unchanged except richer diagnostics can be reused. |

## Decided Approach / 確定方針

### Design Decision

確定: Add structured LoCoMo event-time metadata at indexing time, propagate it through Legacy retrieval items, add a retrieval-only diagnostics CLI, and implement temporal rerank as opt-in ablation only. Default `./scripts/locomo_legacy_smoke.sh --skip-neo4j` must continue to use the existing gate thresholds and no temporal boost unless an explicit environment variable or CLI flag enables it.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Parse dates only in answer prompt | Small change | Retrieval ranking and recall diagnostics still cannot use event time | **Rejected**: fixes answer surface, not candidate quality |
| Hard temporal filter | Can reduce irrelevant contexts | Missing or misparsed dates would remove useful evidence and hurt open_domain | **Rejected**: external temporal rerank evidence favors soft additive scoring |
| Enable temporal boost by default | May improve temporal F1 immediately | Could lower open_domain and change baseline without ablation | **Rejected**: default smoke must remain stable |
| Retrieval diagnostics inside `runner.py` | Reuses existing loop | Couples LLM answer benchmark to retrieval-only measurement | **Rejected**: create separate CLI to keep smoke unchanged |
| **Metadata + recall CLI + opt-in boost (Adopted)** | Low risk, measurable, prepares later entity/fact issues | Requires several modules | **Adopted**: isolates retrieval quality from answer model quality |

### Key Decisions from Discussion

1. **Use `dateutil.parser.parse` for LoCoMo natural language session timestamps** — Reason: dataset uses strings like `8:56 pm on 20 July, 2023`, not ISO timestamps.
2. **Store event metadata on chunks as `valid_at`, `event_time_iso`, `event_time_text`, and `session_index`** — Reason: `valid_at` supports existing memory semantics, while explicit fields make diagnostics readable.
3. **Preserve existing fallback behavior** — Reason: if parsing fails, retrieval must still work with file mtime and must not crash indexing.
4. **Add retrieval diagnostics as `python -m benchmarks.locomo.retrieval_diagnostics`** — Reason: LLM-free measurement should run independently from smoke.
5. **Temporal boost is disabled by default** — Reason: Phase 1-3 showed that changing default behavior without ablation can degrade adversarial and overall F1.
6. **Ablation compares baseline retrieval and temporal-boost retrieval in one JSON** — Reason: implementer and reviewer need a direct before/after diff without running answer LLM.

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/rag/indexer.py` | Modify | Parse LoCoMo-style episode headings during markdown heading chunking and attach event metadata. |
| `benchmarks/locomo/adapter.py` | Modify | Propagate `valid_at`, `event_time_iso`, `event_time_text`, `session_index`, and `event_time_parse_error` through retrieval dicts, pipeline items, context metadata, and diagnostics. |
| `core/memory/retrieval/temporal.py` | New | Implement opt-in soft temporal boost helpers and query temporal-intent detection. |
| `core/memory/retrieval/pipeline.py` | Modify | Accept optional temporal boost settings and apply additive scoring before confidence gate while preserving defaults. |
| `benchmarks/locomo/retrieval_diagnostics.py` | New | LLM-free CLI that reports category-level retrieval recall and temporal ablation deltas. |
| `tests/unit/...` | Modify/New | Add focused tests for date parsing, metadata propagation, temporal boost disabled default, and recall metrics. |
| `tests/integration/test_locomo_legacy_smoke.py` | Modify | Add guardrail that default smoke settings keep temporal boost disabled. |

#### Change 1: Parse LoCoMo Session Heading Metadata

**Target**: `core/memory/rag/indexer.py`

The markdown heading chunker must call a helper after `_extract_metadata()` for episode chunks:

```python
# Before
metadata = self._extract_metadata(...)

# After
metadata = self._extract_metadata(...)
if memory_type == "episodes":
    self._apply_episode_heading_event_time(metadata, heading)
```

The helper must recognize this exact heading family:

```text
## Session 10 - 8:56 pm on 20 July, 2023
## Session 10 — 8:56 pm on 20 July, 2023
```

Expected metadata for parse success:

```json
{
  "session_index": 10,
  "event_time_text": "8:56 pm on 20 July, 2023",
  "event_time_iso": "2023-07-20T20:56:00+09:00",
  "valid_at": 1689854160.0,
  "event_time_parse_error": false
}
```

Timezone handling is fixed: use local timezone from `core.time_utils.ensure_aware()` for naive parsed datetimes. No UTC conversion is required for `event_time_iso`; store the aware ISO string returned by the project time utility.

Parse failure behavior:

```json
{
  "session_index": 10,
  "event_time_text": "unknown date",
  "event_time_iso": "",
  "event_time_parse_error": true
}
```

On parse failure, do not override existing `valid_at`.

#### Change 2: Propagate Metadata Through Legacy Retrieval

**Target**: `benchmarks/locomo/adapter.py`

`_pipeline_item_from_adapter_hit()` must include these optional fields when present:

```python
for key in (
    "valid_at",
    "event_time_iso",
    "event_time_text",
    "session_index",
    "event_time_parse_error",
):
    if key in meta:
        item[key] = meta[key]
```

`_adapter_hit_from_pipeline_item()` must place the same fields back into `metadata`. Result JSON diagnostics must expose `top_retrieval_score` as today and may include a new `top_event_time_iso` field when the top context has one.

#### Change 3: Retrieval-Only Diagnostics CLI

**Target**: `benchmarks/locomo/retrieval_diagnostics.py`

Add a CLI:

```bash
python -m benchmarks.locomo.retrieval_diagnostics \
  --mode scope_all \
  --conversations 1 \
  --top-k 10 \
  --ceiling-top-k 50 \
  --output /tmp/locomo_retrieval_diag
```

Required output JSON fields:

```json
{
  "config": {
    "mode": "scope_all",
    "conversations": 1,
    "top_k": 10,
    "ceiling_top_k": 50,
    "temporal_boost": false
  },
  "summary": {
    "answer_token_recall_at_10": 0.0,
    "answer_token_recall_at_50": 0.0,
    "all_answer_tokens_present_at_10": 0.0,
    "all_answer_tokens_present_at_50": 0.0,
    "by_category": {
      "temporal": {
        "count": 37,
        "answer_token_recall_at_10": 0.0,
        "answer_token_recall_at_50": 0.0
      }
    }
  },
  "results": []
}
```

Metric definition:

- Use `benchmarks.locomo.metrics._stemmed_tokens()` for gold answer tokens and context tokens.
- Exclude category 5 from recall aggregates because the correct behavior is abstain.
- `answer_token_recall_at_k` is the fraction of gold tokens found in concatenated top-k contexts.
- `all_answer_tokens_present_at_k` is `1.0` when every gold token is present in top-k contexts, else `0.0`.
- Store per-question `context_count`, `top_retrieval_score`, `top_event_time_iso`, `answer_token_recall_at_10`, and `answer_token_recall_at_50`.

Execution model:

- Run exact smoke-compatible retrieval with `top_k=10`.
- Run ceiling retrieval with `top_k=50`.
- Do not call any answer LLM.
- Reuse `AnimaWorksLoCoMoAdapter` and `load_dataset`.

#### Change 4: Opt-In Temporal Rerank Ablation

**Target**: `core/memory/retrieval/temporal.py` and `core/memory/retrieval/pipeline.py`

Add a dataclass:

```python
@dataclass(frozen=True)
class TemporalBoostConfig:
    enabled: bool = False
    boost: float = 0.05
    max_boost: float = 0.10
    category: int | None = None
```

Behavior:

- If `enabled` is false, return candidates unchanged.
- If `category != 2`, return candidates unchanged.
- If a candidate lacks `valid_at` and `event_time_iso`, return it unchanged.
- Preserve `base_score`.
- Add `temporal_boost` and `score = base_score + temporal_boost`.
- Temporal boost is additive and capped at `max_boost`.
- First implementation boost rule is fixed: category 2 candidates with valid event metadata receive `boost=0.05`; candidates whose content or event_time text contains a four-digit year also present in the question receive an additional `0.05`, capped at `0.10`.

Pipeline integration:

- Add optional `temporal_boost: TemporalBoostConfig | None = None` argument to `RetrievalPipeline.run()`.
- Apply boost after RRF merge and before cross-encoder rerank.
- Do not change existing call sites unless explicitly passing a config.
- Existing default behavior must be byte-for-byte equivalent for candidate order when `temporal_boost` is absent.

LoCoMo adapter integration:

- Add env var `LOCOMO_TEMPORAL_BOOST=1` to enable temporal boost only for category 2.
- Default is disabled.
- Retrieval diagnostics CLI must run both baseline and boosted modes when `--temporal-ablation` is passed.

### Edge Cases

| Case | Handling |
|------|----------|
| `dateutil` unavailable | The helper sets `event_time_parse_error=true`, keeps existing `valid_at`, and logs at debug level. |
| Session heading uses hyphen instead of em dash | The regex accepts both ` - ` and ` — `. |
| Session date is `unknown date` | Store `event_time_text`, set parse error true, do not override `valid_at`. |
| Preamble chunk before first session | No session metadata is added. |
| Category 5 adversarial | Retrieval recall aggregates exclude it; temporal boost returns unchanged. |
| All gold answer tokens empty after normalization | Per-question recall fields are `null`; item is excluded from aggregate denominators. |
| Temporal boost changes score below confidence gate | Gate uses boosted score only when boost is explicitly enabled; default smoke gate uses existing score. |

## Implementation Plan

### Phase 1: Event-Time Metadata Extraction

| # | Task | Target |
|---|------|--------|
| 1-1 | Add `_apply_episode_heading_event_time()` helper | `core/memory/rag/indexer.py` |
| 1-2 | Call helper in `_chunk_by_markdown_headings()` for `memory_type == "episodes"` | `core/memory/rag/indexer.py` |
| 1-3 | Add unit tests for success, hyphen/em dash, unknown date, and no dateutil fallback | `tests/unit/...` |

**Completion condition**: LoCoMo-style session headings produce `valid_at`, `event_time_iso`, `event_time_text`, and `session_index` metadata without breaking existing `## HH:MM` episode chunk tests.

### Phase 2: Metadata Propagation

| # | Task | Target |
|---|------|--------|
| 2-1 | Preserve event fields in `_pipeline_item_from_adapter_hit()` | `benchmarks/locomo/adapter.py` |
| 2-2 | Preserve event fields in `_adapter_hit_from_pipeline_item()` | `benchmarks/locomo/adapter.py` |
| 2-3 | Add diagnostics for top event time | `benchmarks/locomo/adapter.py`, `benchmarks/locomo/runner.py` |

**Completion condition**: Scope_all result JSON contains event metadata for retrieved chunks where the source session date was parseable.

### Phase 3: Retrieval Diagnostics CLI

| # | Task | Target |
|---|------|--------|
| 3-1 | Add recall metric helpers using `_stemmed_tokens()` | `benchmarks/locomo/retrieval_diagnostics.py` |
| 3-2 | Add CLI args and JSON writer | `benchmarks/locomo/retrieval_diagnostics.py` |
| 3-3 | Add tests for category 5 exclusion and token recall math | `tests/unit/benchmarks/...` |

**Completion condition**: The CLI runs without LLM credentials and writes category-level recall@10 and recall@50 for `conv-26`.

### Phase 4: Temporal Boost Ablation

| # | Task | Target |
|---|------|--------|
| 4-1 | Add `TemporalBoostConfig` and scoring helper | `core/memory/retrieval/temporal.py` |
| 4-2 | Wire optional boost into `RetrievalPipeline.run()` | `core/memory/retrieval/pipeline.py` |
| 4-3 | Enable LoCoMo boost only through env/CLI opt-in | `benchmarks/locomo/adapter.py`, `benchmarks/locomo/retrieval_diagnostics.py` |
| 4-4 | Add default-disabled guardrail tests | `tests/integration/test_locomo_legacy_smoke.py` |

**Completion condition**: Default smoke path produces no temporal boost fields, while diagnostics with `--temporal-ablation` reports baseline-vs-boosted deltas.

## Scope

### In Scope

- Legacy LoCoMo `scope_all` path.
- Event-time metadata extraction from LoCoMo-style session headings.
- Metadata propagation through vector, graph, BM25, RRF, rerank, and result diagnostics.
- LLM-free retrieval recall CLI.
- Opt-in temporal boost ablation for category 2.
- Unit and integration tests for default-disabled behavior.

### Out of Scope

- Updating deepseek baseline JSON — Reason: this issue adds measurement and opt-in ranking only.
- Enabling temporal boost in default smoke — Reason: open_domain regression risk must be measured first.
- Entity-aware retrieval — Reason: parent issue tracks it as the next child.
- Atomic fact extraction / dual index — Reason: larger write-path change, handled by later child.
- Neo4j adapter parity implementation — Reason: first child targets Legacy `scope_all`; Neo4j can consume the same metadata format later.
- LLM judge evaluation — Reason: current smoke is token F1 fixed.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Date parsing assigns wrong timezone | Temporal diagnostics become noisy | Use `ensure_aware()` consistently and store original `event_time_text` for inspection. |
| Metadata propagation changes dedup keys | Retrieval order could change unexpectedly | Do not include event fields in `legacy_result_key`; only carry fields as payload. |
| Temporal boost hides weak semantic matches | Incorrect temporal candidates could move up | Boost is opt-in, category 2 only, capped at 0.10, and disabled in default smoke. |
| Recall metric over-penalizes paraphrases | Diagnostic may understate retrieval quality | Label metric as token recall, not correctness; keep answer smoke as final gate. |
| CLI runtime grows due top_k=50 ceiling | Developer feedback slows | No LLM calls; reuse existing adapter; print per-conversation progress only. |

## Acceptance Criteria

- [ ] `core/memory/rag/indexer.py` extracts `valid_at`, `event_time_iso`, `event_time_text`, and `session_index` from LoCoMo session headings.
- [ ] Existing episode `## HH:MM` chunk behavior remains covered by tests and unchanged.
- [ ] `benchmarks/locomo/adapter.py` preserves event metadata through `_pipeline_item_from_adapter_hit()` and `_adapter_hit_from_pipeline_item()`.
- [ ] `python -m benchmarks.locomo.retrieval_diagnostics --mode scope_all --conversations 1 --top-k 10 --ceiling-top-k 50 --output /tmp/locomo_retrieval_diag` runs without answer LLM credentials.
- [ ] Retrieval diagnostics JSON includes category-level `answer_token_recall_at_10`, `answer_token_recall_at_50`, `all_answer_tokens_present_at_10`, and `all_answer_tokens_present_at_50`.
- [ ] Category 5 is excluded from retrieval recall aggregate denominators.
- [ ] Temporal boost is disabled by default in `RetrievalPipeline.run()` and LoCoMo smoke.
- [ ] `LOCOMO_TEMPORAL_BOOST=1` or diagnostics `--temporal-ablation` enables category 2 temporal boost only.
- [ ] Default `./scripts/locomo_legacy_smoke.sh --skip-neo4j` still uses deepseek baseline thresholds and does not enable temporal boost.
- [ ] Targeted unit/integration tests pass.

## Verification Commands

```bash
.venv/bin/python -m ruff check \
  core/memory/rag/indexer.py \
  core/memory/retrieval/pipeline.py \
  core/memory/retrieval/temporal.py \
  benchmarks/locomo/adapter.py \
  benchmarks/locomo/retrieval_diagnostics.py
```

```bash
pytest \
  tests/unit/benchmarks/test_locomo_retrieval_diagnostics.py \
  tests/unit/test_memory_indexer.py \
  tests/unit/test_retrieval_pipeline.py \
  tests/integration/test_locomo_legacy_smoke.py::test_phase13_regression_guardrails_without_llm \
  -q
```

```bash
python -m benchmarks.locomo.retrieval_diagnostics \
  --mode scope_all \
  --conversations 1 \
  --top-k 10 \
  --ceiling-top-k 50 \
  --temporal-ablation \
  --output /tmp/locomo_retrieval_diag
```

## References

- `docs/issues/20260602_locomo-memory-score-improvement-parent.md` — Parent roadmap.
- `benchmarks/locomo/adapter.py:149` — LoCoMo session markdown builder.
- `benchmarks/locomo/adapter.py:343` — Pipeline item conversion point.
- `benchmarks/locomo/adapter.py:418` — Legacy retrieval entrypoint.
- `core/memory/rag/indexer.py:597` — episode chunking selection.
- `core/memory/rag/indexer.py:682` — current time heading parser.
- `core/memory/rag/indexer.py:944` — current `valid_at` extraction and fallback.
- `core/memory/retrieval/pipeline.py:66` — RRF merge point before rerank.
- `core/memory/retrieval/confidence_gate.py:19` — confidence gate behavior to preserve.
- `benchmarks/locomo/metrics.py:74` — LoCoMo token F1 helper tokens.
- `benchmarks/locomo/baselines/legacy_scope_all_deepseek_v4_flash_20260525.json` — deepseek baseline guardrail.
- https://docs.mem0.ai/core-concepts/memory-evaluation — Memory evaluation and LoCoMo result context.
- https://mem0.ai/blog/introducing-temporal-reasoning-in-mem0 — Soft temporal reranking reference.
- https://arxiv.org/abs/2501.13956 — Zep / Graphiti temporal knowledge graph reference.
- https://arxiv.org/abs/2502.12110 — A-Mem memory note and linking reference.
