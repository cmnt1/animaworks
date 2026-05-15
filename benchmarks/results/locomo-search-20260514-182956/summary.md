# LoCoMo Memory Search Evaluation

**Date**: 2026-05-14T18:29:56
**Git HEAD**: `19f93f35`
**Dataset**: `benchmarks/locomo/data/locomo10.json`
**Conversations**: 10 / 10
**Questions evaluated**: 1540 non-adversarial; 446 adversarial excluded from search metrics
**Top-K**: 10
**Output directory**: `benchmarks/results/locomo-search-20260514-182956`

## Method

- Metric: evidence coverage, not generated-answer F1. It measures whether retrieved contexts contain normalized/stemmed content tokens from the LoCoMo gold answer.
- Primary score: average answer-token recall@10. Support scores: partial hit@10, strong hit@10 (>=50% recall), exact answer substring hit@10, latency, and retrieved context size.
- Category 5/adversarial questions are excluded because the desired behavior is abstention rather than finding an evidence span.
- Neo4j was run through the current `Neo4jGraphBackend.retrieve(scope="all")` path, with a no-op extractor so that LLM unavailability does not block episode ingestion. This evaluates the implemented search path over episode memory, not full extracted Fact/Entity graph quality.

## Overall Results

| Mode | Recall@10 | Strong hit@10 | Exact hit@10 | Avg latency | Avg items | Avg chars |
|---|---:|---:|---:|---:|---:|---:|
| `legacy_vector` | 76.5% | 83.8% | 35.3% | 16.7 ms | 10.00 | 31377 |
| `legacy_vector_graph` | 76.5% | 83.8% | 35.3% | 17.0 ms | 10.00 | 31377 |
| `legacy_scope_all` | 81.3% | 87.5% | 41.4% | 18.0 ms | 10.00 | 30599 |
| `neo4j_scope_all_episode_only` | 50.6% | 52.5% | 25.4% | 82.2 ms | 3.57 | 11036 |

## Category Breakdown

### legacy_scope_all

| Category | Count | Recall@10 | Strong hit@10 | Exact hit@10 |
|---|---:|---:|---:|---:|
| multi_hop | 282 | 70.0% | 78.0% | 20.6% |
| temporal | 321 | 74.5% | 86.6% | 20.9% |
| complex | 96 | 35.9% | 38.5% | 18.8% |
| open_domain | 841 | 92.9% | 96.7% | 58.7% |

### neo4j_scope_all_episode_only

| Category | Count | Recall@10 | Strong hit@10 | Exact hit@10 |
|---|---:|---:|---:|---:|
| multi_hop | 282 | 49.5% | 56.0% | 14.2% |
| temporal | 321 | 11.2% | 7.2% | 2.5% |
| complex | 96 | 18.6% | 18.8% | 8.3% |
| open_domain | 841 | 69.6% | 72.4% | 39.8% |

## Pairwise: Neo4j vs Legacy scope_all

- Mean recall delta: -30.7pp
- Per-question wins/losses/ties for Neo4j: 67 / 681 / 792 (n=1540)
- Category deltas: complex -17.3pp, multi_hop -20.5pp, open_domain -23.3pp, temporal -63.3pp

## Interpretation

- Legacy `scope_all` remains stronger for raw memory search on LoCoMo: it combines vector retrieval with BM25 over session text via RRF, so exact names, dates, and rare keywords are recovered well.
- Current Neo4j `scope=all` episode-only search is usable for broad semantic/open-domain lookup, but it loses a large amount of temporal and complex-query evidence. The biggest observed drop is temporal recall.
- This run does not prove the full Neo4j Fact/Entity graph is weak after the latest ontology work; full graph evaluation needs a working extraction/answer LLM. It does show that the current fallback/raw-episode Neo4j search path is not yet competitive with legacy `scope_all`.
- The key implementation gap exposed by this benchmark is raw episode lexical retrieval in Neo4j `scope=all`: facts/entities have fulltext search, but episode search is effectively vector-centered in this path, while legacy uses BM25 over episodes.

## Previous Answer-F1 Baseline

- Existing result `benchmarks/results/locomo-20260508-191025/summary.md` used 1 conversation and `openai/qwen3.6-27b`: legacy_scope_all 67.1% F1 vs neo4j_full 41.3% F1, with Neo4j full marked FAIL and -25.8pp versus legacy.
- That older run included answer/extraction model errors, so it should be treated as directional rather than final acceptance evidence.

## LLM Availability

- Neo4j Bolt health check passed locally.
- `/v1/models` on local/vLLM endpoints lists DeepSeek models, but short chat completion probes timed out after 20s with no bytes received. Therefore a full generated-answer Locomo rerun was not reliable in this environment.

