# LoCoMo Benchmark Comparison

**Date**: 2026-05-09T12:03:06
**Answer Model**: openai/qwen3.6-27b
**Conversations**: 1
**Top-K**: 10
**Total Time**: 60762s

## Results

| Run | Overall F1 | multi_hop | temporal | open_domain | complex | adversarial | AC |
|-----|-----------|-----------|----------|-------------|---------|-------------|-----|
| legacy_scope_all | 67.1% | 40.5% | 57.4% | 73.2% | 39.6% | 91.5% | PASS |
| neo4j_full | 41.3% | 41.9% | 50.5% | 46.1% | 18.6% | 32.6% | FAIL |
| neo4j_no_reranker | 45.6% | 23.4% | 37.3% | 34.7% | 16.0% | 91.5% | PASS |
| neo4j_no_bfs | 55.4% | 39.2% | 46.7% | 47.0% | 34.6% | 91.5% | PASS |
| neo4j_no_invalidation | 52.9% | 37.5% | 41.7% | 44.3% | 29.5% | 91.5% | PASS |

## Acceptance Criteria

**Threshold**: F1 ≥ 45%

**Neo4j Full Result**: F1 = 41.3% → **FAIL ❌**
**Neo4j vs Legacy**: -25.8pp

## Ablation Analysis

- **neo4j_no_reranker**: F1 = 45.6% (Δ = --4.3pp from full)
- **neo4j_no_bfs**: F1 = 55.4% (Δ = --14.1pp from full)
- **neo4j_no_invalidation**: F1 = 52.9% (Δ = --11.6pp from full)
