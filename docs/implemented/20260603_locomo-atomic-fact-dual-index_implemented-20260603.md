# LoCoMo Atomic Fact Dual Index — raw episode と短文 fact を opt-in 統合する

## Overview

LoCoMo Legacy `scope_all` は raw episode chunk のみを検索対象にしているため、open_domain / multi_hop で短い answer token が長い会話 chunk に埋もれやすい。親 Issue Phase 3 の最初の実装単位として、LoCoMo adapter に ADD-only atomic fact index を追加し、default 無効の `LOCOMO_FACT_INDEX` ablation として raw episode retrieval に統合する。

この Issue は production Legacy 全体の fact extraction ではなく、LoCoMo smoke 改善のための測定可能な最小実装である。既存の production 向け Issue `docs/issues/20260522_legacy-atomic-fact-extraction.md` は将来の本実装として残す。

## Problem / Background

### Current State

- Phase 1 と Phase 2 により `event_time` metadata と entity boost の opt-in ablation は追加済みだが、検索対象は raw episode chunk のままである。
- `AnimaWorksLoCoMoAdapter.ingest_conversation()` は `episodes/{sample}.md` だけを生成し、`memory_type="episodes"` で索引する — `benchmarks/locomo/adapter.py:349`。
- `scope_all` retrieval は episode vector、episode graph、episode BM25 の3リストだけを RRF に渡す — `benchmarks/locomo/adapter.py:514`。
- pipeline item 変換は `memory_type` を `"episodes"` に固定しており、別 collection を混ぜられない — `benchmarks/locomo/adapter.py:390`。
- BM25 cache は episode markdown section だけを対象にする — `benchmarks/locomo/adapter.py:565`。
- indexer は `memory_type="facts"` を whole-file chunk として扱えるため、fact ごとに1ファイルを書けば core indexer の大改造なしで collection を追加できる — `core/memory/rag/indexer.py:573`。
- retrieval-only diagnostics は temporal/entity ablation には対応しているが、fact index ablation と `top_memory_type` / `fact_count` 記録がない — `benchmarks/locomo/retrieval_diagnostics.py:76`。

### Root Cause

1. **符号化粒度が粗い** — LoCoMo conversation は session 単位の markdown chunk で検索され、短い事実が長い context に埋もれる。
2. **dual index を受ける adapter metadata がない** — `_pipeline_item_from_adapter_hit()` が `memory_type="episodes"` を固定しているため、facts collection を RRF に混ぜても由来を保持できない。
3. **fact index の失敗分離がない** — production LLM fact extraction をそのまま入れると、LLM/JSON parsing 失敗が retrieval-only run を止める危険がある。
4. **測定単位がない** — live deepseek smoke は 1.5-3 時間かかるため、fact index の検索効果を先に短時間で確認する ablation が必要である。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `benchmarks/locomo/adapter.py` | Direct | ingest と `scope_all` retrieval が episodes 専用で、facts collection を混ぜられない。 |
| `benchmarks/locomo/retrieval_diagnostics.py` | Direct | fact index の retrieval-only ablation と diagnostics 出力がない。 |
| `core/memory/rag/indexer.py` | Indirect | facts は whole-file chunk になるため、fact 1件1ファイル方式なら既存実装を利用できる。 |
| `core/memory/retrieval/pipeline.py` | No change | RRF input list を増やせば dual index は既存 pipeline で扱える。 |
| `benchmarks/locomo/runner.py` | No change | default 無効のため smoke 実行経路は既定では変えない。 |

## Decided Approach / 確定方針

### Design Decision

確定: LoCoMo 専用の deterministic ADD-only fact record generator を追加し、`LOCOMO_FACT_INDEX=1` のときだけ `animas/locomo_bench/facts/*.md` を生成して `memory_type="facts"` で索引する。fact は LLM では抽出せず、LoCoMo turn text を sentence 単位に分割して短い fact document として保存する。`scope_all` は episode vector / graph / BM25 に fact vector / fact BM25 を追加して既存 `RetrievalPipeline` に渡す。fact generation または indexing が失敗した場合は warning を出して facts をスキップし、episode retrieval を継続する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Production LLM FactExtractor をこの Issue で接続する | Mem0/Zep 型の抽出に近い | LLM credential、prompt、JSON validation、dedup、invalidations が絡み、retrieval-only smoke の失敗面が大きい | **Rejected**: 最初の実装単位として blast radius が大きい |
| `docs/issues/20260522_legacy-atomic-fact-extraction.md` をそのまま実装する | production 機能まで進む | `search_memory scope=facts`、consolidation、session hook、i18n prompt まで含み、LoCoMo 改善の測定サイクルから外れる | **Rejected**: 親 Issue Phase 3 の最小 child ではない |
| facts を episodes markdown に追記する | 実装が小さい | raw episode と distilled fact の score / memory_type / ablation を分離できない | **Rejected**: dual index の測定ができない |
| facts を1つの大きい markdown にまとめる | ファイル数が少ない | `facts` は indexer 上 whole-file chunk になり、短文 fact の粒度を失う | **Rejected**: 短文 retrieval 改善の目的に反する |
| **fact 1件1 markdown + opt-in RRF 統合 (Adopted)** | core indexer 変更を避けつつ短文 chunk と memory_type を分離できる | fact file 数は増える | **Adopted**: LoCoMo 1 conversation smoke では管理可能で、default 挙動を維持できる |

### Key Decisions from Discussion

1. **fact index は default 無効** — Reason: Phase 1-3 の教訓として、default smoke の adversarial / confidence gate 挙動を測定前に変えない。
2. **fact extraction は deterministic turn/sentence split に限定** — Reason: LLM extraction の失敗や variability を retrieval-only diagnostics から切り離す。
3. **fact 1件1 markdown file** — Reason: `core/memory/rag/indexer.py` の existing whole-file chunk strategy を利用して fact 粒度を保つ。
4. **RRF に fact vector と fact BM25 を追加** — Reason: 既存 `RetrievalPipeline` を変更せず、candidate list を増やすだけで raw episode と distilled fact を統合できる。
5. **fact 失敗は non-fatal** — Reason: 親 Issue の completion condition「fact extraction failure が retrieval-only run を止めない」を満たすため。
6. **live answer smoke は default enable 前の gate** — Reason: この Issue では retrieval-only ablation を必須にし、数時間の deepseek smoke は default 有効化判断の前提として扱う。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `benchmarks/locomo/fact_index.py` | New | LoCoMo conversation から deterministic fact records を生成し、`facts/*.md` に frontmatter つきで保存する。 |
| `benchmarks/locomo/adapter.py` | Modify | `LOCOMO_FACT_INDEX` helper、facts directory、fact ingest/index、fact BM25、metadata propagation、scope_all RRF 統合を追加する。 |
| `benchmarks/locomo/retrieval_diagnostics.py` | Modify | `--fact-ablation`、`fact_index` config、`fact_ablation` result、`fact_count`、`top_memory_type` を出力する。 |
| `tests/unit/benchmarks/test_locomo_fact_index.py` | New | fact record generation、stable id、frontmatter writing を検証する。 |
| Existing adapter/diagnostics tests | Modify | default-disabled helper、memory_type propagation、fact ablation CLI/config を検証する。 |
| `core/memory/rag/indexer.py` | No change | fact 1件1 markdown 方式で existing whole-file chunk を利用する。 |
| `core/memory/retrieval/pipeline.py` | No change | ranked list を追加するだけで対応する。 |

#### Fact Record Shape

```json
{
  "fact_id": "sha1-prefix",
  "text": "Caroline: I attended the LGBTQ support group.",
  "valid_at": "2023-05-07T00:00:00+00:00",
  "event_time_iso": "2023-05-07T00:00:00+00:00",
  "session_index": 3,
  "turn_index": 12,
  "sentence_index": 0,
  "speaker": "Caroline",
  "source_episode": "episodes/conv-26.md",
  "entities": ["Caroline", "LGBTQ support group"],
  "confidence": 0.7
}
```

#### Environment Flag

```bash
LOCOMO_FACT_INDEX=1 python -m benchmarks.locomo.retrieval_diagnostics \
  --mode scope_all --conversations 1 --top-k 10 --ceiling-top-k 10
```

`--fact-ablation` は baseline (`fact_index=false`) と boosted (`fact_index=true`) を同じ JSON に出力する。

### Edge Cases

| Case | Handling |
|------|----------|
| `conversation` に text がない turn | `blip_caption` または `query` があれば fact 化し、どちらもなければ skip する。 |
| sentence split 後に短すぎる text | 空文字と2文字未満は skip する。 |
| session date parse 失敗 | `event_time_iso` と `valid_at` は空文字にし、fact 自体は保存する。 |
| speaker 名がない | speaker は `"Unknown"` として保存し、text には prefix を付ける。 |
| duplicate fact | deterministic `fact_id` が同一なら existing file を上書きせず skip する。 |
| fact generation/indexing exception | warning を出し、`_last_fact_count=0`、fact BM25 cache empty として episode retrieval を継続する。 |
| `LOCOMO_FACT_INDEX` disabled | facts directory は作成してよいが、fact generation/indexing と scope_all への追加は行わない。 |
| category 5 adversarial | fact index は retrieval candidate のみを増やす。confidence gate/prompt/abstain logic は変更しない。 |

## Implementation Plan

### Phase 1: Fact Record Generator

| # | Task | Target |
|---|------|--------|
| 1-1 | `LocomoFactRecord` dataclass と deterministic `fact_id` を追加する | `benchmarks/locomo/fact_index.py` |
| 1-2 | LoCoMo session/turn/sentence を fact records に変換する | `benchmarks/locomo/fact_index.py` |
| 1-3 | YAML frontmatter つき markdown writer を追加する | `benchmarks/locomo/fact_index.py` |

**Completion condition**: fixed sample から fact records が生成され、同一入力で stable id と metadata が再現する。

### Phase 2: Adapter Dual Index

| # | Task | Target |
|---|------|--------|
| 2-1 | `locomo_fact_index_enabled()` と facts directory/cache state を追加する | `benchmarks/locomo/adapter.py` |
| 2-2 | ingest 時に opt-in fact generation/indexing を行い、失敗時は episode ingest を継続する | `benchmarks/locomo/adapter.py` |
| 2-3 | `memory_type` を pipeline item と adapter hit metadata に伝播する | `benchmarks/locomo/adapter.py` |
| 2-4 | `scope_all` に fact vector と fact BM25 ranked lists を追加する | `benchmarks/locomo/adapter.py` |

**Completion condition**: `LOCOMO_FACT_INDEX=1` の retrieval で `metadata.memory_type="facts"` の context が返り、disabled 時は既存結果形状を保つ。

### Phase 3: Diagnostics and Tests

| # | Task | Target |
|---|------|--------|
| 3-1 | `--fact-ablation` と `fact_index` config を追加する | `benchmarks/locomo/retrieval_diagnostics.py` |
| 3-2 | per-question `fact_count` と `top_memory_type` を出力する | `benchmarks/locomo/retrieval_diagnostics.py` |
| 3-3 | unit/integration tests を追加・更新する | `tests/` |
| 3-4 | 1 conversation retrieval-only fact ablation を実行して errors=0 と deltas を記録する | CLI |

**Completion condition**: tests が通り、retrieval-only `--fact-ablation` JSON が `fact_ablation.summary` / `fact_ablation.deltas` を含む。

## Scope

### In Scope

- LoCoMo Legacy adapter 専用の deterministic fact dual index。
- `LOCOMO_FACT_INDEX` opt-in flag。
- `scope_all` への fact vector / fact BM25 RRF 統合。
- retrieval-only diagnostics の fact ablation。
- fact extraction/indexing failure の non-fatal fallback。

### Out of Scope

- production `search_memory scope=facts` 追加 — Reason: `docs/issues/20260522_legacy-atomic-fact-extraction.md` の範囲。
- consolidation/session boundary LLM fact extraction — Reason: LoCoMo retrieval ablation には不要で、失敗面が大きい。
- contradiction invalidation / valid_until 更新 — Reason: ADD-only fact index の次段階。
- fact index の default 有効化 — Reason: live deepseek smoke F1 で退行しないことを確認してから判断する。
- answer prompt / confidence gate の変更 — Reason: Phase 1-3 で adversarial 退行済みのため、この Issue では触らない。

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| fact index が noisy candidates を増やす | open_domain/multi_hop 以外や adversarial の F1 退行 | default 無効、`--fact-ablation` で retrieval-only に限定して測る。 |
| fact file 数が増えて ingest が遅くなる | diagnostics 実行時間増加 | LoCoMo 1 conversation scope に限定し、fact 1件1ファイルはこの Issue のみの測定実装とする。 |
| deterministic split が「事実」以外も保存する | retrieval noise | speaker/session metadata と BM25/vector RRF に任せ、production LLM extraction は別 Issue に分離する。 |
| fact indexing failure が run を止める | regression harness が不安定化 | `try/except` で warning + fallback、errors は retrieval failure のみで増やす。 |
| retrieval recall が answer F1 に直結しない | 誤った default 有効化 | acceptance は retrieval-only まで、default enable は live smoke で別判断とする。 |

## Acceptance Criteria

- [ ] `benchmarks/locomo/fact_index.py` が deterministic fact records と markdown writer を提供する。
- [ ] `LOCOMO_FACT_INDEX` は default disabled で、既存 smoke の default path を変えない。
- [ ] enabled 時、LoCoMo ingest で fact records が1件以上生成され、`memory_type="facts"` collection に索引される。
- [ ] fact generation/indexing exception は non-fatal で、episode ingest/retrieval が継続する。
- [ ] `scope_all` enabled 時、episode vector / graph / BM25 と fact vector / fact BM25 が RRF input に入る。
- [ ] pipeline output metadata に `memory_type` が保持され、diagnostics が `top_memory_type` と `fact_count` を出力する。
- [ ] `benchmarks.locomo.retrieval_diagnostics --fact-ablation` が baseline と fact-enabled summary/deltas/errors を同一 JSON に出力する。
- [ ] unit/integration tests が追加・更新され、関連 tests が pass する。
- [ ] 1 conversation retrieval-only fact ablation を実行し、errors=0 と category 別 deltas を記録する。

## References

- `docs/issues/20260602_locomo-memory-score-improvement-parent.md` — Parent roadmap Phase 3.
- `docs/issues/20260522_legacy-atomic-fact-extraction.md` — Broader production fact extraction issue kept out of scope.
- `benchmarks/locomo/adapter.py:349` — current episode-only ingest.
- `benchmarks/locomo/adapter.py:390` — current pipeline item memory_type hardcoding.
- `benchmarks/locomo/adapter.py:514` — current scope_all episode vector/graph/BM25 retrieval.
- `benchmarks/locomo/adapter.py:565` — current episode-only BM25 cache.
- `benchmarks/locomo/retrieval_diagnostics.py:76` — current retrieval-only harness.
- `benchmarks/locomo/retrieval_diagnostics.py:304` — current ablation CLI flags.
- `core/memory/rag/indexer.py:573` — memory_type chunking strategy.
- https://docs.mem0.ai/core-concepts/memory-evaluation — Mem0 LoCoMo evaluation and memory decomposition reference.
- https://arxiv.org/abs/2501.13956 — Graphiti/Zep temporal knowledge graph memory reference.
- https://arxiv.org/abs/2502.12110 — A-Mem agentic memory reference.
