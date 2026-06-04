# Legacy LoCoMo Regression Analysis and Multi-Hop Retrieval Fix — score deltasを再現可能にし、legacy multi-hop retrievalをfact-firstで回復する

## Overview

Legacy LoCoMo の recent memory expansion 後、overall F1 は改善した一方で category 5 を除いた通常質問では regression が出ている。今回の修正では Neo4j を拡張せず、legacy の LoCoMo 計測・retrieval diagnostics・multi-hop retrieval 経路を整備し、fact index を主軸にした改善を安全に進められる状態にする。

## Problem / Background

### Current State

- before/after の同条件測定では、after default は overall F1 が `31.66%` → `34.47%` に上がったが、cat5除外 F1 は `25.00%` → `22.11%` に下がった。
- feature-on では overall F1 `33.84%`、cat5除外 F1 `25.88%` で、通常質問はわずかに改善するが multi_hop は before から `-4.11pt` だった。
- retrieval-only diagnostics では fact index が multi_hop recall@10 を `+18.45pt` 改善しており、最も有効な retrieval lever である。
- entity boost は same-run ablation で全体 recall delta が `+0.19pt` 程度に留まり、answer F1 では multi_hop / open_domain の悪化例も出ている。
- LoCoMo runner は answer timeout / retry count / checkpoint を CLI から制御できず、LLM timeout による blank prediction が before/after 比較を不安定にしている。

### Root Cause

1. Full answer F1 の比較が ad hoc で再現しにくい — `benchmarks/locomo/runner.py:143` は単一 run JSON を書くが、複数 JSON の category delta、blank count、worst/best per-question diff を出す標準ツールがない。
2. Answer generation が長時間待ち・固定 retry になっている — `benchmarks/locomo/adapter.py:841` の `_complete_sync()` は retry 3 回固定で timeout を渡さず、`benchmarks/locomo/runner.py:258` から制御できない。
3. Intermediate checkpoint がない — `benchmarks/locomo/runner.py:313` はメモリ上に結果を溜め、mode 完了後に `benchmarks/locomo/runner.py:409` で書くため、長時間 run の途中失敗で差分分析に使える partial result が残らない。
4. `scope_all` の multi-hop 改善経路が fact index に十分寄っていない — `benchmarks/locomo/adapter.py:650` は `LOCOMO_FACT_INDEX` 有効時に facts scope を含めるが、category 1 の bridge/fact-first 調整や diagnostics 上の feature-on 比較が未整備である。
5. Entity boost が汎用 token overlap を拾いやすい — `core/memory/retrieval/entity.py:121` は content tokens と 2/3-grams を entity set に追加し、`core/memory/retrieval/entity.py:148` は query entity が metadata 由来でなくても query 本文から補完するため、multi-hop で一般語の一致が順位を壊す可能性がある。
6. Retrieval diagnostics が combined feature-on regression を直接出せない — `benchmarks/locomo/retrieval_diagnostics.py:81` は fact/entity/entity-aware 個別 ablation は扱えるが、feature-on combined と per-question regression report がない。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `benchmarks/locomo/compare_results.py` | Direct | before/after result JSON と retrieval diagnostics JSON を比較する新規 CLI を追加する。 |
| `benchmarks/locomo/runner.py` | Direct | answer timeout / max retries / checkpoint metadata を LoCoMo answer run で制御可能にする。 |
| `benchmarks/locomo/adapter.py` | Direct | answer call knobs と category 1 fact-first / stricter entity config を legacy adapter に渡す。 |
| `benchmarks/locomo/retrieval_diagnostics.py` | Direct | combined feature-on ablation と per-question delta を出す。 |
| `core/memory/retrieval/entity.py` | Direct | generic content token 由来の noisy boost を抑える設定を追加する。 |
| `tests/` | Direct | comparison CLI、runner knobs、entity boost guard、diagnostics shape を固定する。 |

## Decided Approach / 確定方針

### Design Decision

確定: Neo4j 側は触らず、legacy LoCoMo の計測再現性と retrieval ranking を同じ Issue で修正する。まず before/after JSON と retrieval diagnostics JSON を deterministic に比較する CLI を追加し、LLM answer timeout / retry / checkpoint を runner から制御可能にする。その上で multi-hop は entity boost 増量ではなく fact index / fact BM25 / fact vector を主軸にし、category 1 の entity boost は metadata-aware かつ generic token を抑制する config に変更する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Neo4j adapter を拡張する | graph retrieval の表現力を使える | user の目的は legacy の拡張であり、現行スコアも legacy が高い | **Rejected**: 今回は legacy を脳科学ベースで発展させる |
| entity boost weight を単純に上げる | 実装が小さい | 実測で entity ablation の効果が小さく、multi_hop / open_domain F1 の悪化例がある | **Rejected**: noisy overlap を増幅するだけになりやすい |
| Full LLM F1 だけを acceptance にする | 最終指標に近い | timeout / blank / adversarial category に強く左右され、retrieval 改善の原因が見えない | **Rejected**: cat5除外・retrieval recall・blank count を併記する |
| LLM entity extraction を入れる | 抽出精度が上がる可能性がある | LoCoMo run の latency と失敗要因を増やし、retrieval-only diagnostics の決定性を壊す | **Rejected**: deterministic legacy retrieval 修正に限定する |
| **Comparison tooling + fact-first multi-hop fix (Adopted)** | 原因分析と改善を同時に検証できる | 変更範囲は複数モジュールにまたがる | **Adopted**: 今回の regression を安全に潰す最短経路 |

### Key Decisions from Discussion

1. **legacy を拡張対象にする** — Reason: user は Neo4j 拡張ではなく、能力が高い legacy に脳科学ベース・Neo4j 的考え方を取り込みたい。
2. **single Issue にする** — Reason: score regression analysis と multi-hop retrieval fix は同じ before/after 証跡で評価すべき。
3. **fact index を multi-hop の主軸にする** — Reason: retrieval-only diagnostics で fact index が multi-hop recall@10 を `+18.45pt` 改善している。
4. **entity boost は stricter にする** — Reason: generic token overlap による順位破壊を防ぎ、category 1 regression を抑える。
5. **LLM run の不安定性を明示的に測る** — Reason: blank prediction 数が before/after の解釈を汚すため、timeout/retry/checkpoint と blank count を標準化する。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `benchmarks/locomo/compare_results.py` | New | LoCoMo result JSON の before/after 比較 CLI。summary delta、cat5除外 delta、blank count、category delta、per-question worst/best regression、Markdown 出力を提供する。 |
| `benchmarks/locomo/runner.py` | Modify | `--answer-timeout`, `--answer-max-retries`, `--checkpoint-every` を追加し、config と partial result に記録する。 |
| `benchmarks/locomo/adapter.py` | Modify | `_complete_sync()` に timeout / max_retries を渡せるようにし、runner から adapter に設定する。category 1 の feature-on retrieval では fact-first と stricter entity config を使う。 |
| `benchmarks/locomo/retrieval_diagnostics.py` | Modify | `--feature-on-ablation` と per-question delta を追加し、fact/entity/entity-aware combined の recall impact を一つの JSON に出す。 |
| `core/memory/retrieval/entity.py` | Modify | `EntityBoostConfig` に generic content token 抑制用の設定を追加し、metadata query entities がない category 1 では汎用語だけで boost しない。 |
| `tests/unit/benchmarks/test_locomo_compare_results.py` | New | compare CLI の summary/category/per-question/blank/Markdown 出力を fixture JSON で検証する。 |
| `tests/unit/test_locomo_adapter.py` | Modify | answer knobs と LoCoMo env/config の伝播を検証する。 |
| `tests/unit/core/memory/test_entity_boost.py` | New/Modify | stricter entity boost が generic token overlap で加点しないことを検証する。 |
| `tests/unit/benchmarks/test_locomo_retrieval_diagnostics.py` | Modify | feature-on ablation JSON shape と delta 計算を検証する。 |
| `tests/integration/test_locomo_legacy_smoke.py` | Modify | default path が壊れていないこと、feature flags が明示時だけ効くことを確認する。 |
| `benchmarks/locomo/neo4j_adapter.py` | No change | 今回は legacy 拡張が目的のため変更しない。 |

### Edge Cases

| Case | Handling |
|------|----------|
| result JSON に `summary` がない | `results` から summary を再計算し、warning を Markdown に出す。 |
| before/after で質問集合が違う | `(sample_id, question_index, question)` を key にして common / before-only / after-only counts を出す。 |
| prediction が空文字または missing | blank prediction として count し、F1 は既存値があればその値、なければ 0 として扱う。 |
| category 5 | overall には含めるが、cat5-excluded summary を必ず別に出す。 |
| answer timeout が未指定 | 既存挙動と互換にし、LiteLLM 側 timeout は渡さない。 |
| answer max retries が 0 | 1 attempt として実行し、backoff しない。 |
| checkpoint 書き込み中に失敗 | benchmark 本体は継続し、recoverable error として stderr/log に出す。 |
| feature-on ablation | `LOCOMO_FACT_INDEX=1`, `LOCOMO_ENTITY_BOOST=1`, `LOCOMO_ENTITY_AWARE_GRAPH=1` を same-run context で一時的に設定し、終了後に環境を復元する。 |
| query/candidate の generic token overlap のみ | category 1 の entity boost では加点しない。 |

## Implementation Plan

### Phase 1: Comparison Tooling

| # | Task | Target |
|---|------|--------|
| 1-1 | LoCoMo result JSON を読み、summary がなければ `compute_summary()` で再計算する loader を追加する | `benchmarks/locomo/compare_results.py` |
| 1-2 | overall / cat5-excluded / category deltas / blank counts / error counts を計算する | `benchmarks/locomo/compare_results.py` |
| 1-3 | common question key ごとの F1 delta、changed prediction、worst/best regressions を出す | `benchmarks/locomo/compare_results.py` |
| 1-4 | JSON と Markdown の両方を出力できる CLI にする | `benchmarks/locomo/compare_results.py` |
| 1-5 | fixture JSON で unit tests を追加する | `tests/unit/benchmarks/test_locomo_compare_results.py` |

**Completion condition**: before/after result JSON を指定すると、cat5除外 delta、blank counts、worst/best per-question diff が deterministic に出る。

### Phase 2: Stable Answer Runner Knobs

| # | Task | Target |
|---|------|--------|
| 2-1 | `_complete_sync()` に optional `timeout` / `max_retries` を追加し、LiteLLM に timeout を渡す | `benchmarks/locomo/adapter.py` |
| 2-2 | adapter constructor または setter で answer timeout / max retries を保持する | `benchmarks/locomo/adapter.py` |
| 2-3 | runner CLI に `--answer-timeout`, `--answer-max-retries`, `--checkpoint-every` を追加する | `benchmarks/locomo/runner.py` |
| 2-4 | mode result config と checkpoint JSON に knobs / partial results / current summary を記録する | `benchmarks/locomo/runner.py` |
| 2-5 | timeout/retry/checkpoint の unit tests を追加する | `tests/unit/test_locomo_adapter.py`, `tests/unit/benchmarks/` |

**Completion condition**: manual monkeypatch なしで `--answer-timeout 60 --answer-max-retries 0` のような比較 run を再現でき、partial JSON が途中経過を残す。

### Phase 3: Multi-Hop Retrieval Fix

| # | Task | Target |
|---|------|--------|
| 3-1 | category 1 feature-on 時に fact index を優先的に使う retrieval config / metadata を整理する | `benchmarks/locomo/adapter.py` |
| 3-2 | `EntityBoostConfig` に generic content token 抑制設定を追加する | `core/memory/retrieval/entity.py` |
| 3-3 | LoCoMo category 1 では query-derived generic tokens だけで boost しない config を渡す | `benchmarks/locomo/adapter.py` |
| 3-4 | fact/entity/entity-aware combined feature-on ablation を追加する | `benchmarks/locomo/retrieval_diagnostics.py` |
| 3-5 | per-question retrieval delta を diagnostics JSON に出し、multi_hop/open_domain regression を見つけやすくする | `benchmarks/locomo/retrieval_diagnostics.py` |

**Completion condition**: feature-on retrieval diagnostics で multi_hop recall が baseline を下回らず、fact index の改善が combined run でも観測できる。

### Phase 4: Verification

| # | Task | Target |
|---|------|--------|
| 4-1 | targeted unit tests を実行する | `pytest tests/unit/benchmarks/test_locomo_compare_results.py tests/unit/benchmarks/test_locomo_retrieval_diagnostics.py tests/unit/test_locomo_adapter.py tests/unit/core/memory/test_entity_boost.py -q` |
| 4-2 | LoCoMo legacy smoke を実行する | `pytest tests/integration/test_locomo_legacy_smoke.py -q` |
| 4-3 | 1 conversation retrieval diagnostics feature-on ablation を実行する | `python -m benchmarks.locomo.retrieval_diagnostics --mode scope_all --conversations 1 --top-k 10 --ceiling-top-k 10 --feature-on-ablation` |
| 4-4 | 既存 before/after JSON で compare CLI を実行し、Markdown report を生成する | `python -m benchmarks.locomo.compare_results ...` |

**Completion condition**: targeted tests と diagnostics smoke が pass し、compare report が生成される。

## Scope

### In Scope

- Legacy LoCoMo result comparison CLI。
- Answer timeout / retry / checkpoint knobs。
- Retrieval diagnostics の combined feature-on ablation。
- category 1 multi-hop 向け fact-first / stricter entity boost。
- Unit tests、integration smoke、retrieval-only diagnostics smoke。

### Out of Scope

- Neo4j adapter の変更 — Reason: user 方針は legacy 拡張。
- Production default で feature flags を有効化すること — Reason: full 10 conversations の安定評価前に default behavior を変えない。
- Full 199-question LLM run を CI gate にすること — Reason: 実行時間と provider timeout に依存する。
- 新しい LLM entity extraction — Reason: deterministic retrieval diagnostics を維持する。
- prompt 大改修や judge scoring 改修 — Reason: retrieval regression fix から外れる。

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| timeout を渡すことで provider 互換性が壊れる | answer run が失敗する | timeout 未指定では既存通り渡さず、指定時のみ LiteLLM kwargs に含める。 |
| checkpoint が大きくなる | 長時間 run の I/O が増える | `--checkpoint-every` 指定時だけ有効化し、default は無効にする。 |
| fact-first が open_domain を傷つける | category 4 F1 が下がる | category 1 を主対象にし、diagnostics で open_domain delta も必ず出す。 |
| stricter entity boost で既存 entity ablation の改善が消える | small recall gain が減る | fact index の改善が主目的。entity boost は regression guard として扱う。 |
| comparison CLI が複数 schema に対応しきれない | 古い run JSON が読めない | `summary` missing fallback と `results` based computation を実装する。 |

## Acceptance Criteria

- [ ] `python -m benchmarks.locomo.compare_results BEFORE.json AFTER.json --output report.json --markdown report.md` が成功し、overall / cat5-excluded / category / blank / per-question deltas を出す。
- [ ] compare CLI は `summary` がない result JSON でも `results` から summary を再計算する。
- [ ] runner は `--answer-timeout`, `--answer-max-retries`, `--checkpoint-every` を受け取り、config と checkpoint に記録する。
- [ ] `_complete_sync()` は timeout 未指定では既存互換、指定時のみ LiteLLM に timeout を渡す。
- [ ] `LOCOMO_FACT_INDEX=1` の category 1 retrieval で facts scope が使われ、diagnostics に fact/top memory metadata が残る。
- [ ] category 1 entity boost は generic token overlap のみでは candidate を加点しない。
- [ ] `python -m benchmarks.locomo.retrieval_diagnostics --mode scope_all --conversations 1 --top-k 10 --ceiling-top-k 10 --feature-on-ablation` が `feature_on_ablation.summary`, `feature_on_ablation.deltas`, `feature_on_ablation.per_question_deltas` を JSON に出す。
- [ ] targeted unit tests が pass する。
- [ ] `pytest tests/integration/test_locomo_legacy_smoke.py -q` が pass する。
- [ ] Neo4j adapter に変更が入っていない。

## References

- `benchmarks/locomo/adapter.py:607` — Legacy `scope_all` retrieval entrypoint and feature flag integration.
- `benchmarks/locomo/adapter.py:650` — fact scope override currently depends on `LOCOMO_FACT_INDEX`.
- `benchmarks/locomo/adapter.py:669` — entity boost config currently uses default entity extraction.
- `benchmarks/locomo/adapter.py:841` — answer completion retry loop lacks timeout / retry knobs.
- `benchmarks/locomo/runner.py:248` — runner calls retrieve / answer per question.
- `benchmarks/locomo/runner.py:313` — results are appended in memory before final write.
- `benchmarks/locomo/runner.py:409` — mode result JSON is written only after mode completion.
- `benchmarks/locomo/retrieval_diagnostics.py:81` — retrieval-only diagnostics runner.
- `core/memory/retrieval/entity.py:121` — content tokens are added to entity set.
- `core/memory/retrieval/entity.py:148` — query text extraction is used when explicit query entities are not required.
- `/tmp/locomo-full-before-after/before_785239ad_full_conv1_default_timeout60_1try/2026-06-04T10-30-51_scope_all.json` — before measurement under timeout60 / 1 attempt.
- `/tmp/locomo-full-before-after/after_64a620a9_full_conv1_default_timeout60_1try/2026-06-04T12-29-58_scope_all.json` — after default measurement under same condition.
- `/tmp/locomo-full-before-after/after_64a620a9_full_conv1_feature_on_timeout60_1try/2026-06-04T14-28-25_scope_all.json` — after feature-on measurement under same condition.
- `/tmp/locomo_retrieval_diag_issue3_top10/2026-06-03T12-33-13_scope_all_retrieval_diagnostics.json` — fact index retrieval-only improvement evidence.
